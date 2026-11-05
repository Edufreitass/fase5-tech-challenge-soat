"""fn-veiculos-worker: LIBERAR_VEICULO, AGUARDANDO_RETIRADA e
BAIXAR_VEICULO (passos da saga)."""

import os
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config

from shared.logger import criar_logger
from vehicles.adapters.dynamodb.repository import DynamoDBVeiculoRepository
from vehicles.application.saga import PassosVeiculo

logger = criar_logger("veiculos-worker")


@lru_cache(maxsize=1)
def _repositorio() -> DynamoDBVeiculoRepository:
    cliente = boto3.client(
        "dynamodb", config=Config(retries={"mode": "standard", "max_attempts": 5})
    )
    return DynamoDBVeiculoRepository(cliente, os.environ["VEICULOS_TABELA"])


def handler(evento: dict[str, Any], _contexto: Any) -> dict[str, Any]:
    acao = str(evento.get("acao"))
    logger.info("acao", extra={"acao": acao, "vendaId": evento.get("vendaId")})
    PassosVeiculo(_repositorio()).executar(acao, evento["veiculoId"], evento["vendaId"])
    return {}
