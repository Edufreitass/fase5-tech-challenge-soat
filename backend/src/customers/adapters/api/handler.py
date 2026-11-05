"""fn-clientes-api: cadastro e consulta do proprio perfil. Nunca
le
a
chave privada.
"""

import os
from datetime import date
from functools import lru_cache
from typing import Annotated, Any

import boto3
from aws_lambda_powertools.event_handler import Response
from aws_lambda_powertools.event_handler.openapi.params import Body
from botocore.config import Config
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from customers.adapters.cognito.identity import CognitoIdentidade
from customers.adapters.cognito.removal import CognitoRemocao
from customers.adapters.crypto.fields import CifradorSealedBox, HasherHmac
from customers.adapters.dynamodb.repository import DynamoDBClienteRepository
from customers.adapters.dynamodb.sales import VendasEmAndamentoDynamo
from customers.adapters.internal.customer import InvocadorClientesInterno
from customers.application.data_protection import AnonimizarCliente, ExcluirCliente, ExportarDados
from customers.application.query import ConsultarCliente
from customers.application.registration import CadastrarCliente
from customers.application.update import AtualizarCliente, MudancasPerfil, RegistrarConsentimento
from customers.domain.models import (
    Cliente,
    ConsentimentoEntrada,
    Endereco,
    Finalidade,
    NovoCliente,
    RgEntrada,
)
from customers.domain.ports import DiretorioIdentidade
from shared import parameters as parametros
from shared.errors import NaoAutenticado
from shared.events import PublicadorSns
from shared.http import AppRevenda, processar
from shared.masking import mascarar_cpf
from shared.metrics import ACESSOS_DADOS_PESSOAIS, emitir
from shared.security import Papel

app = AppRevenda("clientes-api")


class _Modelo(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", str_strip_whitespace=True
    )


class EnderecoModelo(_Modelo):
    cep: Annotated[str, Field(max_length=9)]
    logradouro: Annotated[str, Field(max_length=120)]
    numero: Annotated[str, Field(max_length=10)]
    complemento: Annotated[str | None, Field(max_length=60)] = None
    bairro: Annotated[str, Field(max_length=80)]
    cidade: Annotated[str, Field(max_length=80)]
    uf: Annotated[str, Field(min_length=2, max_length=2)]


class RgModelo(_Modelo):
    numero: Annotated[str, Field(max_length=20)]
    orgao_emissor: Annotated[str, Field(max_length=10)]
    uf: Annotated[str, Field(min_length=2, max_length=2)]


class ConsentimentoModelo(_Modelo):
    versao_termo: Annotated[str, Field(max_length=20)]
    aceito: bool
    finalidades: Annotated[list[Finalidade], Field(min_length=1, max_length=2)]


class ClienteEntrada(_Modelo):
    nome_completo: Annotated[str, Field(max_length=120)]
    cpf: Annotated[str, Field(max_length=14, examples=["529.982.247-25"])]
    data_nascimento: date
    telefone: Annotated[str, Field(max_length=16, examples=["+5511987654321"])]
    endereco: EnderecoModelo
    rg: RgModelo | None = None
    consentimento: ConsentimentoModelo


@lru_cache(maxsize=1)
def _repositorio() -> DynamoDBClienteRepository:
    cliente = boto3.client(
        "dynamodb", config=Config(retries={"mode": "standard", "max_attempts": 5})
    )
    return DynamoDBClienteRepository(cliente, os.environ["CLIENTES_TABELA"])


@lru_cache(maxsize=1)
def _identidade() -> DiretorioIdentidade:
    return CognitoIdentidade(boto3.client("cognito-idp"), os.environ["POOL_CLIENTES_ID"])


def _cifrador() -> CifradorSealedBox:
    versao = int(parametros.obter("pii/versao-atual"))
    return CifradorSealedBox(parametros.obter(f"pii/chave-publica-v{versao}"), versao)


@lru_cache(maxsize=1)
def _vendas_em_andamento() -> VendasEmAndamentoDynamo:
    return VendasEmAndamentoDynamo(boto3.client("dynamodb"), os.environ["VENDAS_TABELA"])


def _caso_cadastro() -> CadastrarCliente:
    return CadastrarCliente(
        repositorio=_repositorio(),
        cifrador=_cifrador(),
        hasher=HasherHmac(parametros.obter("segredos/cpf-hmac", segredo=True)),
        versao_termo_vigente=parametros.obter("params/versao-termo-vigente"),
    )


def _resposta(c: Cliente) -> dict[str, Any]:
    e = c.endereco
    return {
        "id": c.id,
        "nomeCompleto": c.nome_completo,
        "cpf": mascarar_cpf(c.cpf_final),
        "dataNascimento": c.data_nascimento.isoformat(),
        "email": c.email,
        "telefone": c.telefone,
        "endereco": {
            "cep": e.cep,
            "logradouro": e.logradouro,
            "numero": e.numero,
            "complemento": e.complemento,
            "bairro": e.bairro,
            "cidade": e.cidade,
            "uf": e.uf,
        },
        "rg": {"numero": c.rg.numero_mascarado, "orgaoEmissor": c.rg.orgao_emissor, "uf": c.rg.uf}
        if c.rg
        else None,
        "cnh": f"*******{c.cnh_final}" if c.cnh_final else None,
        "consentimentoVigente": {
            "versaoTermo": c.consentimento_vigente.versao_termo,
            "aceitoEm": c.consentimento_vigente.aceito_em,
        },
        "cadastroCompleto": c.cadastro_completo,
        "camposPendentes": list(c.campos_pendentes),
        "status": c.status.value,
    }


def _com_etag(c: Cliente, status: int) -> Response[dict[str, Any]]:
    return Response(
        status_code=status,
        content_type="application/json",
        headers={"ETag": f'"v{c.versao}"', "Location": "/v1/clientes/meu-perfil"},
        body=_resposta(c),
    )


@app.rota(
    "POST", "/clientes", Papel.CLIENTE, summary="Cadastrar o proprio perfil", tags=["Clientes"]
)
def cadastrar_cliente(corpo: Annotated[ClienteEntrada, Body()]) -> Response[dict[str, Any]]:
    sub = app.identidade().sub
    email, verificado = _identidade().obter_email(sub)
    if not email:
        raise NaoAutenticado("Usuario sem e-mail no provedor de identidade.")
    evento = app.current_event
    e, c = corpo.endereco, corpo.consentimento
    comando = NovoCliente(
        id=sub,
        email=email,
        email_verificado=verificado,
        nome_completo=corpo.nome_completo,
        cpf=corpo.cpf,
        data_nascimento=corpo.data_nascimento,
        telefone=corpo.telefone,
        endereco=Endereco(e.cep, e.logradouro, e.numero, e.bairro, e.cidade, e.uf, e.complemento),
        rg=RgEntrada(corpo.rg.numero, corpo.rg.orgao_emissor, corpo.rg.uf) if corpo.rg else None,
        consentimento=ConsentimentoEntrada(c.versao_termo, c.aceito, tuple(c.finalidades)),
        ip=evento.request_context.identity.source_ip or "",
        user_agent=evento.headers.get("User-Agent", ""),
    )
    criado = _caso_cadastro().executar(comando)
    PublicadorSns(
        boto3.client("sns"), os.environ.get("TOPICO_EVENTOS_ARN", ""), app.correlation_id
    ).publicar("ClienteCadastrado", {"clienteId": criado.id})
    return _com_etag(criado, 201)


@app.rota(
    "GET",
    "/clientes/meu-perfil",
    Papel.CLIENTE,
    summary="Consultar o proprio perfil (mascarado)",
    tags=["Clientes"],
)
def meu_perfil() -> Response[dict[str, Any]]:
    vigente = parametros.obter("params/versao-termo-vigente")
    return _com_etag(
        ConsultarCliente(_repositorio()).meu_perfil(app.identidade().sub, vigente), 200
    )


class ClienteEdicao(_Modelo):
    """PATCH parcial; CPF e e-mail nao sao editaveis."""

    nome_completo: Annotated[str | None, Field(max_length=120)] = None
    telefone: Annotated[str | None, Field(max_length=16)] = None
    endereco: EnderecoModelo | None = None
    rg: RgModelo | None = None
    cnh: Annotated[str | None, Field(max_length=14)] = None


class ConsentimentoEntrada2(_Modelo):
    versao_termo: Annotated[str, Field(max_length=20)]
    aceito: bool
    finalidades: Annotated[list[Finalidade], Field(min_length=1, max_length=2)]


@app.rota(
    "PATCH",
    "/clientes/meu-perfil",
    Papel.CLIENTE,
    summary="Atualizar o proprio perfil (If-Match)",
    tags=["Clientes"],
)
def atualizar_perfil(corpo: Annotated[ClienteEdicao, Body()]) -> Response[dict[str, Any]]:
    versao = app.versao_if_match()
    e = corpo.endereco
    mudancas = MudancasPerfil(
        nome_completo=corpo.nome_completo,
        telefone=corpo.telefone,
        endereco=Endereco(e.cep, e.logradouro, e.numero, e.bairro, e.cidade, e.uf, e.complemento)
        if e
        else None,
        rg=RgEntrada(corpo.rg.numero, corpo.rg.orgao_emissor, corpo.rg.uf) if corpo.rg else None,
        cnh=corpo.cnh,
    )
    atualizado = AtualizarCliente(
        _repositorio(),
        _cifrador(),
        _vendas_em_andamento(),
        parametros.obter("params/versao-termo-vigente"),
    ).executar(app.identidade().sub, mudancas, versao)
    return _com_etag(atualizado, 200)


@app.rota(
    "POST",
    "/clientes/meu-perfil/consentimentos",
    Papel.CLIENTE,
    summary="Registrar aceite/revogacao de consentimento",
    tags=["Clientes"],
)
def registrar_consentimento(
    corpo: Annotated[ConsentimentoEntrada2, Body()],
) -> Response[dict[str, Any]]:
    evento = app.current_event
    consentimento, cliente = RegistrarConsentimento(
        _repositorio(),
        HasherHmac(parametros.obter("segredos/cpf-hmac", segredo=True)),
        parametros.obter("params/versao-termo-vigente"),
    ).executar(
        app.identidade().sub,
        corpo.versao_termo,
        corpo.aceito,
        list(corpo.finalidades),
        evento.request_context.identity.source_ip or "",
        evento.headers.get("User-Agent", ""),
    )
    return Response(
        status_code=201,
        content_type="application/json",
        headers={"Location": "/v1/clientes/meu-perfil"},
        body={
            "versaoTermo": consentimento.versao_termo,
            "finalidades": [f.value for f in consentimento.finalidades],
            "aceito": consentimento.aceito,
            "aceitoEm": consentimento.aceito_em,
            "consentimentoVigente": {
                "versaoTermo": cliente.consentimento_vigente.versao_termo,
                "aceitoEm": cliente.consentimento_vigente.aceito_em,
            },
            "cadastroCompleto": cliente.cadastro_completo,
            "camposPendentes": list(cliente.campos_pendentes),
        },
    )


@lru_cache(maxsize=1)
def _vendas_do_cliente() -> VendasEmAndamentoDynamo:
    return VendasEmAndamentoDynamo(boto3.client("dynamodb"), os.environ["VENDAS_TABELA"])


def _anonimizador() -> AnonimizarCliente:
    return AnonimizarCliente(
        _repositorio(),
        _vendas_do_cliente(),
        HasherHmac(parametros.obter("segredos/cpf-hmac", segredo=True)),
        CognitoRemocao(boto3.client("cognito-idp"), os.environ["POOL_CLIENTES_ID"]),
    )


@app.rota(
    "GET",
    "/clientes/meu-perfil/exportacao",
    Papel.CLIENTE,
    summary="Exportar meus dados (LGPD, 1 por 24 h)",
    tags=["Clientes"],
)
def exportar_dados() -> Response[dict[str, Any]]:
    cliente_id = app.identidade().sub
    dados = ExportarDados(
        _repositorio(),
        _vendas_do_cliente(),
        InvocadorClientesInterno(boto3.client("lambda"), os.environ["CLIENTES_INTERNO_FUNCAO"]),
    ).executar(cliente_id)
    PublicadorSns(
        boto3.client("sns"), os.environ.get("TOPICO_EVENTOS_ARN", ""), app.correlation_id
    ).publicar("ExportacaoGerada", {"clienteId": cliente_id})
    emitir(ACESSOS_DADOS_PESSOAIS)
    return Response(
        status_code=200,
        content_type="application/json",
        headers={"Cache-Control": "no-store"},
        body=dados,
    )


@app.rota(
    "DELETE",
    "/clientes/meu-perfil",
    Papel.CLIENTE,
    summary="Excluir/anonimizar meus dados (LGPD)",
    tags=["Clientes"],
)
def excluir_dados() -> Response[str]:
    cliente_id = app.identidade().sub
    anonimizador = _anonimizador()
    ExcluirCliente(_repositorio(), _vendas_do_cliente(), anonimizador).executar(cliente_id)
    PublicadorSns(
        boto3.client("sns"), os.environ.get("TOPICO_EVENTOS_ARN", ""), app.correlation_id
    ).publicar("ClienteAnonimizado", {"clienteId": cliente_id})
    return Response(status_code=204, content_type="application/json", body="")


def handler(evento: dict[str, Any], contexto: Any) -> dict[str, Any]:
    return processar(app, evento, contexto)
