"""fn-webhook-pagamentos: recebe o webhook do gateway (HMAC + anti-
replay +
idempotencia).
"""

import contextlib
import json
import os
import time
from functools import lru_cache
from typing import Any

import boto3
from aws_lambda_powertools.event_handler import Response
from aws_lambda_powertools.utilities.idempotency import (
    DynamoDBPersistenceLayer,
    IdempotencyConfig,
    idempotent_function,
)
from aws_lambda_powertools.utilities.idempotency.exceptions import (
    IdempotencyAlreadyInProgressError,
)
from pydantic import BaseModel, ConfigDict, ValidationError

from payments.adapters.dynamodb.repository import DynamoDBPagamentoRepository
from payments.application.webhook import EventoGateway, ProcessarEventoGateway
from payments.domain.models import TipoEvento
from shared import parameters as parametros
from shared import webhook_signature as assinatura_webhook
from shared.errors import ErroNegocio
from shared.http import AppRevenda, problema, processar
from shared.metrics import PAGAMENTOS_TARDIOS, WEBHOOK_SUSPEITO, emitir
from shared.security import Papel
from shared.sfn import CallbackStepFunctions

app = AppRevenda("webhook-pagamentos")
SETE_DIAS = 7 * 24 * 3600


class EventoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idEvento: str
    tipo: TipoEvento
    idTransacaoExterna: str
    referencia: str
    valorCentavos: int
    sequencia: int
    ocorridoEm: str


class MetricasLog:
    def suspeito(self) -> None:
        app.logger.warning("webhook_suspeito")
        emitir(WEBHOOK_SUSPEITO)

    def pagamento_tardio(self) -> None:
        app.logger.warning("pagamento_tardio")
        emitir(PAGAMENTOS_TARDIOS)


class EstornoAssincrono:
    """Invoca fn-pagamentos-worker (ESTORNAR) de forma assincrona;
    falha
    vai para a DLQ.
    """

    def solicitar_async(self, pagamento_id: str) -> None:
        boto3.client("lambda").invoke(
            FunctionName=os.environ["PAGAMENTOS_WORKER_FUNCAO"],
            InvocationType="Event",
            Payload=json.dumps({"acao": "ESTORNAR", "pagamentoId": pagamento_id}).encode(),
        )


@lru_cache(maxsize=1)
def _repositorio() -> DynamoDBPagamentoRepository:
    return DynamoDBPagamentoRepository(boto3.client("dynamodb"), os.environ["PAGAMENTOS_TABELA"])


@lru_cache(maxsize=1)
def _persistencia() -> DynamoDBPersistenceLayer:
    return DynamoDBPersistenceLayer(table_name=os.environ["IDEMPOTENCIA_TABELA"])


_CONFIG = IdempotencyConfig(event_key_jmespath="idEvento", expires_after_seconds=SETE_DIAS)


def _config() -> IdempotencyConfig:
    return _CONFIG


_CACHE_SEGREDOS: dict[str, Any] = {"ate": 0.0, "valores": []}


def _segredos() -> list[str]:
    """Segredo atual e o da versao imediatamente anterior (rotacao sem
    janela de falha).

    O admin so tem PutParameter: a versao anterior vem do historico do
    proprio parametro (`nome:versao`).
    """
    if time.time() < _CACHE_SEGREDOS["ate"]:
        return list(_CACHE_SEGREDOS["valores"])
    ssm = boto3.client("ssm")
    nome = f"{parametros.prefixo()}/segredos/webhook-hmac-atual"
    atual = ssm.get_parameter(Name=nome, WithDecryption=True)["Parameter"]
    valores = [str(atual["Value"])]
    if int(atual["Version"]) > 1:
        with contextlib.suppress(
            ssm.exceptions.ParameterVersionNotFound, ssm.exceptions.ParameterNotFound
        ):
            anterior = ssm.get_parameter(
                Name=f"{nome}:{int(atual['Version']) - 1}", WithDecryption=True
            )
            valores.append(str(anterior["Parameter"]["Value"]))
    _CACHE_SEGREDOS.update(ate=time.time() + 60, valores=valores)
    return valores


def _caso() -> ProcessarEventoGateway:
    return ProcessarEventoGateway(
        _repositorio(),
        CallbackStepFunctions(boto3.client("stepfunctions")),
        EstornoAssincrono(),
        MetricasLog(),
    )


def _processar(evento: EventoEntrada) -> dict[str, str]:
    """Idempotente por `idEvento` (7 dias). O decorador e montado na
    chamada para criar o cliente
    DynamoDB so quando ha credenciais/regiao (e permitir testes com
    moto)."""

    @idempotent_function(  # type: ignore[untyped-decorator]
        data_keyword_argument="evento", config=_config(), persistence_store=_persistencia()
    )
    def interno(*, evento: EventoEntrada) -> dict[str, str]:
        resultado = _caso().executar(
            EventoGateway(
                evento.idEvento,
                evento.tipo,
                evento.idTransacaoExterna,
                evento.valorCentavos,
                evento.sequencia,
            )
        )
        return {"resultado": resultado.value}

    return interno(evento=evento)  # type: ignore[no-any-return]


@app.rota("POST", "/webhooks/pagamentos", Papel.ANONIMO, include_in_schema=False)
def receber() -> Response[str]:
    corpo = app.current_event.body or ""
    assinatura = app.current_event.headers.get("X-Gateway-Signature")
    if not assinatura_webhook.verificar(assinatura, corpo, _segredos(), int(time.time())):
        app.logger.warning("webhook_suspeito: assinatura invalida")
        emitir(WEBHOOK_SUSPEITO)
        return problema(
            401,
            "nao-autenticado",
            "Assinatura invalida",
            None,
            "/webhooks/pagamentos",
            app.correlation_id,
        )
    try:
        evento = EventoEntrada.model_validate_json(corpo)
    except ValidationError:
        return problema(
            400,
            "requisicao-invalida",
            "Corpo invalido",
            None,
            "/webhooks/pagamentos",
            app.correlation_id,
        )
    chave = app.current_event.headers.get("Idempotency-Key")
    if chave and chave != evento.idEvento:
        return problema(
            400,
            "requisicao-invalida",
            "Idempotency-Key diferente do idEvento",
            None,
            "/webhooks/pagamentos",
            app.correlation_id,
        )
    try:
        resultado = _processar(evento=evento)
    except IdempotencyAlreadyInProgressError:
        return problema(
            409,
            "idempotencia-em-andamento",
            "Evento em processamento",
            None,
            "/webhooks/pagamentos",
            app.correlation_id,
        )
    except ErroNegocio:
        raise
    return Response(status_code=200, content_type="application/json", body=json.dumps(resultado))


def handler(evento: dict[str, Any], contexto: Any) -> dict[str, Any]:
    if contexto is not None:
        _CONFIG.register_lambda_context(contexto)  # expiracao do registro "em andamento"
    return processar(app, evento, contexto)
