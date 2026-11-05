"""fn-vendas-outbox: Stream da tabela `vendas` (CRIADO -> RESERVADO) ->
StartExecution da saga."""

import os
from functools import lru_cache
from typing import Any

import boto3
from boto3.dynamodb.types import TypeDeserializer

from sales.adapters.dynamodb.repository import DynamoDBVendaRepository, de_item
from sales.adapters.saga.handler import PrazosSsm
from sales.application.saga import IniciarSaga
from shared.logger import criar_logger
from shared.sfn import SagaStepFunctions

logger = criar_logger("vendas-outbox")
_DES = TypeDeserializer()


@lru_cache(maxsize=1)
def _iniciar() -> IniciarSaga:
    repo = DynamoDBVendaRepository(
        boto3.client("dynamodb"), os.environ["VENDAS_TABELA"], os.environ["VEICULOS_TABELA"]
    )
    return IniciarSaga(
        repo, SagaStepFunctions(boto3.client("stepfunctions"), os.environ["SAGA_ARN"]), PrazosSsm()
    )


def handler(evento: dict[str, Any], _contexto: Any) -> dict[str, Any]:
    """At-least-once: devolve os itens que falharam
    (ReportBatchItemFailures).
    """
    falhas: list[dict[str, str]] = []
    for registro in evento.get("Records", []):
        try:
            imagem = {k: _DES.deserialize(v) for k, v in registro["dynamodb"]["NewImage"].items()}
            venda = de_item(imagem)
            _iniciar().executar(venda)
            logger.info("saga iniciada", extra={"vendaId": venda.id})
        except Exception:
            logger.exception("falha ao iniciar saga")
            falhas.append({"itemIdentifier": registro["dynamodb"]["SequenceNumber"]})
    return {"batchItemFailures": falhas}
