"""fn-vendas-api: compra (reserva em duas fases), consulta, desistencia
e
retirada.
"""

import os
from functools import lru_cache
from typing import Annotated, Any

import boto3
from aws_lambda_powertools.event_handler import Response
from aws_lambda_powertools.event_handler.openapi.params import Body, Path, Query
from botocore.config import Config
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from customers.adapters.internal.customer import InvocadorClientesInterno
from payments.adapters.dynamodb.repository import DynamoDBPagamentoRepository
from sales.adapters.dynamodb.repository import DynamoDBVendaRepository
from sales.application.purchase import (
    ConfirmarRetirada,
    ConsultarVenda,
    DesistirDaCompra,
    IniciarCompra,
)
from sales.application.query import ListarVendas, ObterDocumentacao
from sales.domain.models import DadosPagamento, EventoVenda, StatusVenda, Venda
from shared import pagination as paginacao
from shared import parameters as parametros
from shared.contracts import Cursor, DocumentacaoRetirada
from shared.errors import RecursoNaoEncontrado, ReservaAtivaExistente, VeiculoIndisponivel
from shared.events import PublicadorSns
from shared.http import AppRevenda, processar
from shared.metrics import ACESSOS_DADOS_PESSOAIS, RESERVAS_CONFLITO, RESERVAS_CRIADAS, emitir
from shared.security import Papel
from shared.sfn import SagaStepFunctions
from shared.time import agora_iso
from vehicles.adapters.dynamodb.repository import DynamoDBVeiculoRepository

app = AppRevenda("vendas-api")
FUNCIONARIOS = (Papel.VENDEDOR, Papel.ADMIN)


class _Modelo(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", str_strip_whitespace=True
    )


class NovaCompra(_Modelo):
    veiculo_id: Annotated[str, Field(min_length=1, max_length=36)]


class DocumentacaoEntrada(_Modelo):
    protocolo: Annotated[str, Field(min_length=3, max_length=60)]
    emitida_em: Annotated[str, Field(max_length=30)]


class ConferenciaEntrada(_Modelo):
    documento_apresentado: Annotated[str, Field(min_length=2, max_length=30)]


class RetiradaEntrada(_Modelo):
    retirada_em: Annotated[str, Field(max_length=30)]
    documentacao: DocumentacaoEntrada
    conferencia: ConferenciaEntrada


@lru_cache(maxsize=1)
def _ddb() -> Any:
    return boto3.client("dynamodb", config=Config(retries={"mode": "standard", "max_attempts": 5}))


@lru_cache(maxsize=1)
def _vendas() -> DynamoDBVendaRepository:
    return DynamoDBVendaRepository(
        _ddb(), os.environ["VENDAS_TABELA"], os.environ["VEICULOS_TABELA"]
    )


@lru_cache(maxsize=1)
def _veiculos() -> DynamoDBVeiculoRepository:
    return DynamoDBVeiculoRepository(_ddb(), os.environ["VEICULOS_TABELA"])


@lru_cache(maxsize=1)
def _clientes() -> InvocadorClientesInterno:
    return InvocadorClientesInterno(boto3.client("lambda"), os.environ["CLIENTES_INTERNO_FUNCAO"])


@lru_cache(maxsize=1)
def _saga() -> SagaStepFunctions:
    return SagaStepFunctions(boto3.client("stepfunctions"), os.environ["SAGA_ARN"])


class LeitorPagamentoDynamo:
    def __init__(self, repo: DynamoDBPagamentoRepository) -> None:
        self._repo = repo

    def por_id(self, pagamento_id: str) -> DadosPagamento | None:
        pg = self._repo.obter(pagamento_id)
        if pg is None:
            return None
        return DadosPagamento(
            pg.id, pg.status.value, pg.pix_copia_e_cola, pg.valor_centavos, pg.expira_em
        )


def _leitor() -> LeitorPagamentoDynamo:
    return LeitorPagamentoDynamo(
        DynamoDBPagamentoRepository(_ddb(), os.environ["PAGAMENTOS_TABELA"])
    )


def _preco(centavos: int) -> str:
    return f"{centavos // 100}.{centavos % 100:02d}"


def _resumo(v: Venda) -> dict[str, Any]:
    return {
        "id": v.id,
        "status": v.status.value,
        "veiculo": v.veiculo_snapshot,
        "precoNegociado": _preco(v.preco_negociado_centavos),
        "reservaExpiraEm": v.reserva_expira_em,
        "pagamento": None,
        "criadoEm": v.criado_em,
    }


def _evento(e: EventoVenda) -> dict[str, Any]:
    corpo: dict[str, Any] = {
        "para": e.para.value,
        "ocorridoEm": e.ocorrido_em,
        "ator": e.ator.value,
    }
    if e.de:
        corpo["de"] = e.de.value
    if e.motivo:
        corpo["motivo"] = e.motivo.value
    return corpo


def _detalhe(v: Venda, pg: DadosPagamento | None, historico: list[EventoVenda]) -> dict[str, Any]:
    return {
        **_resumo(v),
        "clienteId": v.cliente_id,
        "pagamento": {
            "id": pg.id,
            "metodo": pg.metodo,
            "status": pg.status,
            "pixCopiaECola": pg.pix_copia_e_cola,
            "valor": _preco(pg.valor_centavos),
            "expiraEm": pg.expira_em,
        }
        if pg
        else None,
        "retiradaLimiteEm": v.retirada_limite_em,
        "retiradaEm": v.retirada_em,
        "documentacao": v.documentacao,
        "motivoCancelamento": v.motivo_cancelamento.value if v.motivo_cancelamento else None,
        "historico": [_evento(e) for e in historico],
    }


@app.rota(
    "POST", "/vendas", Papel.CLIENTE, summary="Iniciar compra (reserva o veiculo)", tags=["Vendas"]
)
def iniciar_compra(corpo: Annotated[NovaCompra, Body()]) -> Response[dict[str, Any]]:
    prazo = int(parametros.obter("params/prazo-pagamento-segundos"))
    try:
        venda = IniciarCompra(_vendas(), _veiculos(), _clientes(), prazo).executar(
            app.identidade().sub, corpo.veiculo_id, app.correlation_id
        )
    except (VeiculoIndisponivel, ReservaAtivaExistente):
        emitir(RESERVAS_CONFLITO)
        raise
    emitir(RESERVAS_CRIADAS)
    app.logger.info("reserva_criada", extra={"vendaId": venda.id, "veiculoId": venda.veiculo_id})
    return Response(
        status_code=201,
        content_type="application/json",
        headers={"Location": f"/v1/vendas/{venda.id}"},
        body=_resumo(venda),
    )


@app.rota(
    "GET",
    "/vendas/<venda_id>",
    Papel.CLIENTE,
    *FUNCIONARIOS,
    summary="Consultar venda",
    tags=["Vendas"],
)
def consultar_venda(venda_id: Annotated[str, Path()]) -> dict[str, Any]:
    if len(venda_id) > 36:  # noqa: PLR2004
        raise RecursoNaoEncontrado("Venda nao encontrada.")
    identidade = app.identidade()
    venda, pagamento, historico = ConsultarVenda(_vendas(), _leitor()).executar(
        venda_id, solicitante_id=identidade.sub, funcionario=identidade.funcionario
    )
    return _detalhe(venda, pagamento, historico)


@app.rota(
    "POST",
    "/vendas/<venda_id>/desistencia",
    Papel.CLIENTE,
    summary="Desistir da compra",
    tags=["Vendas"],
)
def desistir(venda_id: Annotated[str, Path()]) -> Response[dict[str, Any]]:
    if len(venda_id) > 36:  # noqa: PLR2004
        raise RecursoNaoEncontrado("Venda nao encontrada.")
    DesistirDaCompra(_vendas(), _saga()).executar(venda_id, app.identidade().sub)
    return Response(
        status_code=202,
        content_type="application/json",
        body={"mensagem": "desistencia em processamento"},
    )


@app.rota(
    "POST",
    "/vendas/<venda_id>/retirada",
    *FUNCIONARIOS,
    summary="Confirmar retirada do veiculo",
    tags=["Vendas"],
)
def retirada(
    venda_id: Annotated[str, Path()], corpo: Annotated[RetiradaEntrada, Body()]
) -> Response[dict[str, Any]]:
    if len(venda_id) > 36:  # noqa: PLR2004
        raise RecursoNaoEncontrado("Venda nao encontrada.")
    documentacao: DocumentacaoRetirada = {
        "status": "EMITIDA",
        "protocolo": corpo.documentacao.protocolo,
        "emitidaEm": corpo.documentacao.emitida_em,
        "responsavelId": app.identidade().sub,
        "registradaEm": agora_iso(),
    }
    ConfirmarRetirada(_vendas(), _saga()).executar(venda_id, corpo.retirada_em, documentacao)
    return Response(
        status_code=202,
        content_type="application/json",
        body={"mensagem": "retirada em processamento"},
    )


Limit = Annotated[str | None, Query()]
NextToken = Annotated[str | None, Query(alias="nextToken")]


def _linha(v: Venda, *, com_cliente: bool) -> dict[str, Any]:
    corpo = {
        **_resumo(v),
        "motivoCancelamento": v.motivo_cancelamento.value if v.motivo_cancelamento else None,
        "retiradaEm": v.retirada_em,
    }
    if com_cliente:
        corpo["clienteId"] = v.cliente_id
    return corpo


def _pagina(
    vendas: list[Venda], proxima: dict[str, Any] | None, *, com_cliente: bool
) -> dict[str, Any]:
    return {
        "itens": [_linha(v, com_cliente=com_cliente) for v in vendas],
        "nextToken": paginacao.codificar(proxima, parametros.segredo_cursor())
        if proxima
        else None,
    }


def _cursor(next_token: str | None) -> Cursor | None:
    return (
        paginacao.decodificar_cursor(next_token, parametros.segredo_cursor())
        if next_token
        else None
    )


@app.rota(
    "GET",
    "/vendas",
    *FUNCIONARIOS,
    summary="Listar vendas por status (mais recentes primeiro)",
    tags=["Vendas"],
)
def listar_vendas(
    status: Annotated[StatusVenda, Query()], limit: Limit = None, next_token: NextToken = None
) -> dict[str, Any]:
    vendas, proxima = ListarVendas(_vendas()).por_status(
        status, limite=paginacao.validar_limite(limit), cursor=_cursor(next_token)
    )
    return _pagina(vendas, proxima, com_cliente=True)


@app.rota(
    "GET",
    "/clientes/meu-perfil/vendas",
    Papel.CLIENTE,
    summary="Historico de compras do cliente",
    tags=["Vendas"],
)
def historico_do_cliente(limit: Limit = None, next_token: NextToken = None) -> dict[str, Any]:
    vendas, proxima = ListarVendas(_vendas()).do_cliente(
        app.identidade().sub, limite=paginacao.validar_limite(limit), cursor=_cursor(next_token)
    )
    return _pagina(vendas, proxima, com_cliente=False)


@app.rota(
    "GET",
    "/vendas/<venda_id>/documentacao",
    *FUNCIONARIOS,
    summary="Dados para a documentacao do veiculo",
    tags=["Vendas"],
)
def documentacao(venda_id: Annotated[str, Path()]) -> dict[str, Any]:
    if len(venda_id) > 36:  # noqa: PLR2004
        raise RecursoNaoEncontrado("Venda nao encontrada.")
    identidade = app.identidade()
    papel = "admin" if "admin" in identidade.grupos else "vendedor"
    resultado = ObterDocumentacao(
        _vendas(),
        _veiculos(),
        _clientes(),
        PublicadorSns(
            boto3.client("sns"), os.environ.get("TOPICO_EVENTOS_ARN", ""), app.correlation_id
        ),
    ).executar(venda_id, app.current_event.headers.get("X-Justificativa"), identidade.sub, papel)
    emitir(ACESSOS_DADOS_PESSOAIS)
    return resultado


def handler(evento: dict[str, Any], contexto: Any) -> dict[str, Any]:
    return processar(app, evento, contexto)
