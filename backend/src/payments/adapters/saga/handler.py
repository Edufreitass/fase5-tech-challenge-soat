"""fn-pagamentos-worker: passos da saga (EMITIR_CODIGO,
CANCELAR_CODIGO)
e
ESTORNAR (tambem assincrono).
"""

import os
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config

from customers.adapters.internal.customer import InvocadorClientesInterno
from payments.adapters.dynamodb.repository import DynamoDBPagamentoRepository
from payments.adapters.gateway_http.customer import GatewayHttp
from payments.application.payment import CancelarCodigo, EmitirCodigo, Estornar
from shared.logger import criar_logger

logger = criar_logger("pagamentos-worker")


@lru_cache(maxsize=1)
def _repositorio() -> DynamoDBPagamentoRepository:
    cliente = boto3.client(
        "dynamodb", config=Config(retries={"mode": "standard", "max_attempts": 5})
    )
    return DynamoDBPagamentoRepository(cliente, os.environ["PAGAMENTOS_TABELA"])


@lru_cache(maxsize=1)
def _gateway() -> GatewayHttp:
    credenciais = boto3.Session().get_credentials().get_frozen_credentials()  # type: ignore[union-attr]
    return GatewayHttp(os.environ["GATEWAY_URL"], credenciais, os.environ["AWS_REGION"])  # type: ignore[arg-type]


@lru_cache(maxsize=1)
def _clientes() -> InvocadorClientesInterno:
    return InvocadorClientesInterno(boto3.client("lambda"), os.environ["CLIENTES_INTERNO_FUNCAO"])


def handler(evento: dict[str, Any], _contexto: Any) -> dict[str, Any]:
    acao = evento.get("acao")
    logger.info("acao", extra={"acao": acao, "vendaId": evento.get("vendaId")})
    if acao == "EMITIR_CODIGO":
        return EmitirCodigo(_repositorio(), _gateway(), _clientes()).executar(
            evento["vendaId"],
            evento["clienteId"],
            int(evento["valorCentavos"]),
            int(evento["prazoSegundos"]),
        )
    if acao == "CANCELAR_CODIGO":
        CancelarCodigo(_repositorio(), _gateway()).executar(
            evento["pagamentoId"], evento.get("motivo", "")
        )
        return {}
    if acao == "ESTORNAR":
        Estornar(_repositorio(), _gateway()).executar(evento["pagamentoId"])
        return {}
    raise ValueError(f"acao desconhecida: {acao}")
