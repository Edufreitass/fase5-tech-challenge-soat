"""Adaptador de pagamentos simulados.

A rota `simular` exige JWT de funcionário; webhooks são assinados.
"""

import json
import os
import time
from functools import lru_cache
from typing import Annotated, Any

import boto3
import httpx
from aws_lambda_powertools.event_handler import Response
from aws_lambda_powertools.event_handler.openapi.params import Body, Path
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from shared import parameters as parametros
from shared import webhook_signature as assinatura_webhook
from shared.http import AppRevenda, processar
from shared.security import Papel
from stubs.mock_gateway.adapters.aws import DynamoDBMock, FilaSqs
from stubs.mock_gateway.application.mock import GatewayMock, corpo_json

app = AppRevenda("gateway-mock")
FUNCIONARIOS = (Papel.VENDEDOR, Papel.ADMIN)
TIMEOUT_ENTREGA = 8.0


class _Modelo(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class Pagador(_Modelo):
    nome: Annotated[str, Field(max_length=120)]
    cpf: Annotated[str, Field(max_length=14)]


class CobrancaEntrada(_Modelo):
    referencia: Annotated[str, Field(max_length=64)]
    valor_centavos: Annotated[int, Field(gt=0)]
    pagador: Pagador
    expira_em: Annotated[str, Field(max_length=30)]


class EstornoEntrada(_Modelo):
    id_transacao_externa: Annotated[str, Field(max_length=64)]
    valor_centavos: Annotated[int, Field(gt=0)]


class SimulacaoEntrada(_Modelo):
    resultado: Annotated[str, Field(pattern="^(APROVADO|RECUSADO)$")]
    atraso_segundos: Annotated[int, Field(ge=0, le=900)] = 0
    duplicar: bool = False
    fora_de_ordem: bool = False


@lru_cache(maxsize=1)
def _mock() -> GatewayMock:
    return GatewayMock(
        DynamoDBMock(boto3.client("dynamodb"), os.environ["GATEWAY_MOCK_TABELA"]),
        FilaSqs(boto3.client("sqs"), os.environ["MOCK_WEBHOOKS_URL"]),
    )


@app.rota(
    "POST",
    "/_simulacao/pagamentos/cobrancas",
    Papel.SISTEMA,
    summary="Criar cobranca (mock)",
    tags=["Mock"],
)
def criar_cobranca(corpo: Annotated[CobrancaEntrada, Body()]) -> dict[str, str]:
    # o CPF do pagador nunca e persistido nem logado pelo mock
    return _mock().criar_cobranca(corpo.referencia, corpo.valor_centavos, corpo.expira_em)


@app.rota(
    "POST",
    "/_simulacao/pagamentos/cobrancas/<transacao_id>/cancelar",
    Papel.SISTEMA,
    summary="Cancelar cobranca (mock)",
    tags=["Mock"],
)
def cancelar(transacao_id: Annotated[str, Path()]) -> dict[str, str]:
    _mock().cancelar(transacao_id)
    return {"status": "CANCELADA"}


@app.rota(
    "POST",
    "/_simulacao/pagamentos/estornos",
    Papel.SISTEMA,
    summary="Solicitar estorno (mock)",
    tags=["Mock"],
)
def estornar(corpo: Annotated[EstornoEntrada, Body()]) -> dict[str, str]:
    return _mock().estornar(corpo.id_transacao_externa, corpo.valor_centavos)


@app.rota(
    "POST",
    "/_simulacao/pagamentos/cobrancas/<transacao_id>/simular",
    *FUNCIONARIOS,
    summary="Simular pagamento (mock)",
    tags=["Mock"],
)
def simular(
    transacao_id: Annotated[str, Path()], corpo: Annotated[SimulacaoEntrada, Body()]
) -> Response[dict[str, Any]]:
    n = _mock().simular(
        transacao_id,
        corpo.resultado,
        corpo.atraso_segundos,
        duplicar=corpo.duplicar,
        fora_de_ordem=corpo.fora_de_ordem,
    )
    return Response(
        status_code=202, content_type="application/json", body={"webhooksEnfileirados": n}
    )


def entregar_webhook(evento: dict[str, Any], http: httpx.Client | None = None) -> None:
    """Assina (HMAC) e entrega ao webhook; qualquer resposta diferente
    de
    200 gera nova tentativa.
    """
    corpo = corpo_json(evento)
    segredo = parametros.obter("segredos/webhook-hmac-atual", segredo=True, cache_segundos=60)
    assinatura = assinatura_webhook.assinar(segredo, int(time.time()), corpo)
    cliente = http or httpx.Client(timeout=TIMEOUT_ENTREGA)
    resposta = cliente.post(
        os.environ["WEBHOOK_URL"],
        content=corpo,
        headers={
            "Content-Type": "application/json",
            "X-Gateway-Signature": assinatura,
            "Idempotency-Key": evento["idEvento"],
        },
    )
    resposta.raise_for_status()


def consumir(evento: dict[str, Any]) -> dict[str, Any]:
    falhas: list[dict[str, str]] = []
    for registro in evento["Records"]:
        try:
            entregar_webhook(json.loads(registro["body"]))
        except Exception:
            app.logger.exception("falha ao entregar webhook")
            falhas.append({"itemIdentifier": registro["messageId"]})
    return {"batchItemFailures": falhas}


def handler(evento: dict[str, Any], contexto: Any) -> dict[str, Any]:
    if "Records" in evento and evento["Records"][0].get("eventSource") == "aws:sqs":
        return consumir(evento)
    return processar(app, evento, contexto)
