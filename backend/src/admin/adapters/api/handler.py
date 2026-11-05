"""fn-admin-api: administracao (funcionarios, auditoria, operacoes e
configuracao inicial).
"""

import os
from datetime import datetime
from functools import lru_cache
from typing import Annotated, Any

import boto3
from aws_lambda_powertools.event_handler import Response
from aws_lambda_powertools.event_handler.openapi.params import Body, Path, Query
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from admin.adapters.aws.operations import (
    AuditoriaCloudWatch,
    SagasStepFunctions,
    SegredosSsm,
    SolicitacoesDynamo,
)
from admin.adapters.cognito.directory import CognitoDiretorioFuncionarios
from admin.application.employees import AdministrarFuncionarios
from admin.application.operations import (
    AdministrarSagas,
    ConsultarAuditoria,
    ListarSolicitacoesLgpd,
    RotacionarSegredos,
)
from admin.application.setup import ConfigurarPrimeiroAdministrador
from admin.domain.models import Funcionario, GrupoFuncionario
from shared import pagination as paginacao
from shared import parameters as parametros
from shared.errors import RecursoNaoEncontrado
from shared.events import PublicadorSns
from shared.http import AppRevenda, processar
from shared.security import Papel

app = AppRevenda("admin-api")


class _Modelo(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", str_strip_whitespace=True
    )


class NovoFuncionario(_Modelo):
    nome: Annotated[str, Field(min_length=1, max_length=120)]
    email: Annotated[str, Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
    grupo: GrupoFuncionario


class AtualizacaoFuncionario(_Modelo):
    grupo: GrupoFuncionario | None = None
    ativo: bool | None = None


class FuncionarioResposta(_Modelo):
    id: str
    nome: str
    email: str
    grupos: list[str]
    ativo: bool
    mfa_configurado: bool


class PaginaFuncionariosResposta(_Modelo):
    itens: list[FuncionarioResposta]
    next_token: str | None


@lru_cache(maxsize=1)
def _casos_de_uso() -> AdministrarFuncionarios:
    return AdministrarFuncionarios(
        diretorio=CognitoDiretorioFuncionarios(
            boto3.client("cognito-idp"), os.environ["POOL_FUNCIONARIOS_ID"]
        ),
        eventos=PublicadorSns(boto3.client("sns"), os.environ.get("TOPICO_EVENTOS_ARN", "")),
    )


@lru_cache(maxsize=1)
def _configuracao_inicial() -> ConfigurarPrimeiroAdministrador:
    return ConfigurarPrimeiroAdministrador(
        diretorio=CognitoDiretorioFuncionarios(
            boto3.client("cognito-idp"), os.environ["POOL_FUNCIONARIOS_ID"]
        ),
        eventos=PublicadorSns(boto3.client("sns"), os.environ.get("TOPICO_EVENTOS_ARN", "")),
        email_dono=lambda: parametros.obter("params/administracao-email", cache_segundos=0),
    )


def _resposta(f: Funcionario) -> dict[str, Any]:
    return FuncionarioResposta(
        id=f.id,
        nome=f.nome,
        email=f.email,
        grupos=list(f.grupos),
        ativo=f.ativo,
        mfa_configurado=f.mfa_configurado,
    ).model_dump(by_alias=True)


@app.rota(
    "GET",
    "/configuracao-inicial",
    Papel.ANONIMO,
    summary="Informar se falta criar o primeiro administrador",
    tags=["Administracao"],
)
def situacao_configuracao_inicial() -> dict[str, Any]:
    return {"necessaria": _configuracao_inicial().necessaria()}


@app.rota(
    "POST",
    "/configuracao-inicial",
    Papel.ANONIMO,
    summary="Convidar o administrador declarado na implantacao",
    tags=["Administracao"],
)
def concluir_configuracao_inicial() -> Response[dict[str, Any]]:
    _configuracao_inicial().executar()
    return Response(
        status_code=201,
        content_type="application/json",
        body={"mensagem": "Convite enviado ao administrador declarado na implantacao."},
    )


@app.rota(
    "GET",
    "/administracao/funcionarios",
    Papel.ADMIN,
    summary="Listar funcionarios",
    tags=["Administracao"],
)
def listar_funcionarios(
    grupo: Annotated[GrupoFuncionario | None, Query()] = None,
    limit: Annotated[str | None, Query()] = None,
    next_token: Annotated[str | None, Query(alias="nextToken")] = None,
) -> dict[str, Any]:
    segredo = parametros.segredo_cursor()
    proximo = paginacao.decodificar_texto(next_token, segredo) if next_token else None
    pagina = _casos_de_uso().listar(
        grupo=grupo,
        limite=paginacao.validar_limite(limit),
        proximo=proximo,
        ator_id=app.identidade().sub,
    )
    return {
        "itens": [_resposta(f) for f in pagina.itens],
        "nextToken": paginacao.codificar(pagina.proximo, segredo) if pagina.proximo else None,
    }


@app.rota(
    "POST",
    "/administracao/funcionarios",
    Papel.ADMIN,
    summary="Convidar funcionario",
    tags=["Administracao"],
)
def criar_funcionario(corpo: Annotated[NovoFuncionario, Body()]) -> Response[dict[str, Any]]:
    criado = _casos_de_uso().criar(
        nome=corpo.nome, email=corpo.email, grupo=corpo.grupo, ator_id=app.identidade().sub
    )
    return Response(
        status_code=201,
        content_type="application/json",
        headers={"Location": f"/v1/administracao/funcionarios/{criado.id}"},
        body=_resposta(criado),
    )


@app.rota(
    "PATCH",
    "/administracao/funcionarios/<funcionario_id>",
    Papel.ADMIN,
    summary="Alterar grupo ou ativar/desativar",
    tags=["Administracao"],
)
def atualizar_funcionario(
    funcionario_id: Annotated[str, Path()],
    corpo: Annotated[AtualizacaoFuncionario, Body()],
) -> dict[str, Any]:
    atualizado = _casos_de_uso().atualizar(
        funcionario_id, grupo=corpo.grupo, ativo=corpo.ativo, ator_id=app.identidade().sub
    )
    return _resposta(atualizado)


@lru_cache(maxsize=1)
def _eventos() -> PublicadorSns:
    return PublicadorSns(boto3.client("sns"), os.environ.get("TOPICO_EVENTOS_ARN", ""))


def _cursor(token: str | None) -> str | None:
    return paginacao.decodificar_texto(token, parametros.segredo_cursor()) if token else None


def _token(valor: object) -> str | None:
    return paginacao.codificar(valor, parametros.segredo_cursor()) if valor else None


@app.rota(
    "GET",
    "/administracao/auditoria",
    Papel.ADMIN,
    summary="Consultar a trilha de auditoria (janela de ate 31 dias)",
    tags=["Administracao"],
)
def auditoria(
    cliente_id: Annotated[str | None, Query(alias="clienteId", max_length=64)] = None,
    ator_id: Annotated[str | None, Query(alias="atorId", max_length=64)] = None,
    acao: Annotated[str | None, Query(max_length=64)] = None,
    de: Annotated[datetime | None, Query()] = None,
    ate: Annotated[datetime | None, Query()] = None,
    limit: Annotated[str | None, Query()] = None,
    next_token: Annotated[str | None, Query(alias="nextToken")] = None,
) -> dict[str, Any]:
    trilha = AuditoriaCloudWatch(boto3.client("logs"), os.environ["AUDITORIA_LOG_GROUP"])
    itens, proximo = ConsultarAuditoria(trilha, _eventos()).executar(
        app.identidade().sub,
        cliente_id,
        ator_id,
        acao,
        de,
        ate,
        paginacao.validar_limite(limit),
        _cursor(next_token),
    )
    return {"itens": itens, "nextToken": _token(proximo)}


@app.rota(
    "GET",
    "/administracao/solicitacoes-lgpd",
    Papel.ADMIN,
    summary="Listar solicitacoes LGPD",
    tags=["Administracao"],
)
def solicitacoes_lgpd(
    limit: Annotated[str | None, Query()] = None,
    next_token: Annotated[str | None, Query(alias="nextToken")] = None,
) -> dict[str, Any]:
    fonte = SolicitacoesDynamo(boto3.client("dynamodb"), os.environ["CLIENTES_TABELA"])
    itens, proximo = ListarSolicitacoesLgpd(fonte, _eventos()).executar(
        app.identidade().sub,
        paginacao.validar_limite(limit),
        paginacao.decodificar_cursor(next_token, parametros.segredo_cursor())
        if next_token
        else None,
    )
    return {"itens": itens, "nextToken": _token(proximo)}


def _sagas() -> AdministrarSagas:
    return AdministrarSagas(
        SagasStepFunctions(boto3.client("stepfunctions"), os.environ["SAGA_ARN"]), _eventos()
    )


@app.rota(
    "GET",
    "/administracao/sagas",
    Papel.ADMIN,
    summary="Listar execucoes da saga por status",
    tags=["Administracao"],
)
def listar_sagas(
    status: Annotated[str, Query()] = "FAILED",
    limit: Annotated[str | None, Query()] = None,
    next_token: Annotated[str | None, Query(alias="nextToken")] = None,
) -> dict[str, Any]:
    itens, proximo = _sagas().listar(
        app.identidade().sub, status, paginacao.validar_limite(limit), _cursor(next_token)
    )
    return {"itens": itens, "nextToken": _token(proximo)}


@app.rota(
    "POST",
    "/administracao/vendas/<venda_id>/fluxo/reprocessamento",
    Papel.ADMIN,
    summary="Reprocessar saga com falha",
    tags=["Administracao"],
)
def reprocessar_saga(venda_id: Annotated[str, Path()]) -> Response[dict[str, Any]]:
    if len(venda_id) > 36:  # noqa: PLR2004
        raise RecursoNaoEncontrado("Venda nao encontrada.")
    _sagas().reprocessar(app.identidade().sub, venda_id)
    return Response(
        status_code=202,
        content_type="application/json",
        body={"mensagem": "reprocessamento solicitado"},
    )


def _segredos() -> RotacionarSegredos:
    return RotacionarSegredos(
        SegredosSsm(
            boto3.client("ssm"),
            boto3.client("lambda"),
            parametros.prefixo(),
            os.environ["LGPD_WORKER_FUNCAO"],
        ),
        _eventos(),
    )


@app.rota(
    "POST",
    "/administracao/segredos/webhook/rotacao",
    Papel.ADMIN,
    summary="Rotacionar o segredo HMAC do webhook",
    tags=["Administracao"],
)
def rotacionar_webhook() -> dict[str, int]:
    return {"versao": _segredos().webhook(app.identidade().sub)}


@app.rota(
    "POST",
    "/administracao/chaves-pii/rotacao",
    Papel.ADMIN,
    summary="Rotacionar a chave PII (recifra os dados)",
    tags=["Administracao"],
)
def rotacionar_chave_pii() -> Response[dict[str, int]]:
    versao = _segredos().chave_pii(app.identidade().sub)
    return Response(status_code=202, content_type="application/json", body={"versao": versao})


def handler(evento: dict[str, Any], contexto: Any) -> dict[str, Any]:
    return processar(app, evento, contexto)
