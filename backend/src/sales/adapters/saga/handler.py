"""fn-vendas-worker: REGISTRAR_TOKEN, ATUALIZAR_VENDA, LIBERAR_LOCK
(saga)
e VARREDURA (Scheduler).
"""

import os
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config

from payments.adapters.dynamodb.repository import DynamoDBPagamentoRepository
from sales.adapters.dynamodb.repository import DynamoDBVendaRepository
from sales.application.saga import IniciarSaga, PassosVenda, Varredura
from shared import parameters as parametros
from shared.logger import criar_logger
from shared.metrics import emitir_status_final_de_venda
from shared.sfn import SagaStepFunctions

logger = criar_logger("vendas-worker")


class PrazosSsm:
    def pagamento_segundos(self) -> int:
        return int(parametros.obter("params/prazo-pagamento-segundos"))

    def retirada_segundos(self) -> int:
        return int(parametros.obter("params/prazo-retirada-segundos"))


class TokensPagamentoDynamo:
    def __init__(self, repo: DynamoDBPagamentoRepository) -> None:
        self._repo = repo

    def registrar_token(self, pagamento_id: str, token: str) -> None:
        self._repo.registrar_token(pagamento_id, token)

    def status(self, pagamento_id: str) -> str | None:
        pg = self._repo.obter(pagamento_id)
        return pg.status.value if pg else None


@lru_cache(maxsize=1)
def _ddb() -> Any:
    return boto3.client("dynamodb", config=Config(retries={"mode": "standard", "max_attempts": 5}))


@lru_cache(maxsize=1)
def _vendas() -> DynamoDBVendaRepository:
    return DynamoDBVendaRepository(
        _ddb(), os.environ["VENDAS_TABELA"], os.environ["VEICULOS_TABELA"]
    )


@lru_cache(maxsize=1)
def _saga() -> SagaStepFunctions:
    return SagaStepFunctions(boto3.client("stepfunctions"), os.environ["SAGA_ARN"])


def _passos() -> PassosVenda:
    pagamentos = TokensPagamentoDynamo(
        DynamoDBPagamentoRepository(_ddb(), os.environ["PAGAMENTOS_TABELA"])
    )
    return PassosVenda(_vendas(), _saga(), pagamentos)


def handler(evento: dict[str, Any], _contexto: Any) -> dict[str, Any]:
    acao = evento.get("acao")
    venda_id = str(evento.get("vendaId", ""))
    logger.info("acao", extra={"acao": acao, "vendaId": venda_id})
    if acao == "REGISTRAR_TOKEN":
        _passos().registrar_token(
            evento["etapa"], venda_id, evento["taskToken"], evento.get("pagamentoId")
        )
        return {}
    if acao == "ATUALIZAR_VENDA":
        emitir_status_final_de_venda(evento["para"])
        _passos().atualizar_venda(
            venda_id,
            evento["de"],
            evento["para"],
            motivo=evento.get("motivo"),
            ator=evento.get("ator", "SISTEMA"),
            definir=evento.get("definir") or {},
            prazo_retirada_segundos=evento.get("prazoRetiradaSegundos"),
        )
        return {}
    if acao == "RESOLVER_RETIRADA":
        return {"retiradaRegistrada": _vendas().encerrar_retirada(venda_id)}
    if acao == "LIBERAR_LOCK":
        _passos().liberar_lock(evento["clienteId"], venda_id)
        return {}
    if acao == "VARREDURA":
        return Varredura(_vendas(), IniciarSaga(_vendas(), _saga(), PrazosSsm())).executar()
    raise ValueError(f"acao desconhecida: {acao}")
