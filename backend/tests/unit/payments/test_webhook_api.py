"""Handler HTTP do webhook com idempotencia do Powertools (moto):
evento duplicado e assinatura."""

import json
import os
import time
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from aws_lambda_powertools.utilities import parameters
from moto import mock_aws

from payments.adapters.dynamodb.repository import DynamoDBPagamentoRepository
from payments.adapters.webhook import handler as modulo
from payments.application.payment import EmitirCodigo
from shared import parameters as parametros
from shared import webhook_signature as assinatura_webhook
from tests.tables import criar_tabelas
from tests.unit.payments.test_payments import ClientesFake, GatewayFake, SagaFake

os.environ.setdefault("IDEMPOTENCIA_TABELA", "t-idem")
os.environ.setdefault("PAGAMENTOS_TABELA", "t-pagamentos")
SEGREDO = "segredo-do-webhook"


@pytest.fixture
def amb(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[DynamoDBPagamentoRepository, SagaFake, str]]:
    with mock_aws():
        ddb = boto3.client("dynamodb")
        criar_tabelas(ddb)
        boto3.client("ssm").put_parameter(
            Name="/revenda/dev/segredos/webhook-hmac-atual", Value=SEGREDO, Type="SecureString"
        )
        repo = DynamoDBPagamentoRepository(ddb, "t-pagamentos")
        saga = SagaFake()
        pid = EmitirCodigo(repo, GatewayFake(), ClientesFake()).executar(
            "venda-1", "cli", 1000, 3600
        )["pagamentoId"]
        repo.registrar_token(pid, "tok")
        monkeypatch.setattr(modulo, "_repositorio", lambda: repo)
        monkeypatch.setattr(modulo, "CallbackStepFunctions", lambda _c: saga)
        modulo._persistencia.cache_clear()
        modulo._CACHE_SEGREDOS.update(ate=0.0, valores=[])
        parametros.segredo_cursor.cache_clear()

        parameters.base.DEFAULT_PROVIDERS.clear()  # type: ignore[attr-defined]
        yield repo, saga, pid


class ContextoFake:
    def get_remaining_time_in_millis(self) -> int:
        return 10_000


def chamar(corpo: str, assinatura: str | None, chave: str | None = None) -> tuple[int, Any]:
    headers = {"X-Gateway-Signature": assinatura} if assinatura else {}
    if chave:
        headers["Idempotency-Key"] = chave
    evento = {
        "httpMethod": "POST",
        "path": "/webhooks/pagamentos",
        "resource": "/webhooks/pagamentos",
        "headers": headers,
        "multiValueHeaders": {},
        "queryStringParameters": None,
        "body": corpo,
        "isBase64Encoded": False,
        "requestContext": {"requestId": "r", "stage": "v1"},
    }
    r = modulo.handler(evento, ContextoFake())
    return r["statusCode"], json.loads(r["body"] or "{}")


def evento(repo: DynamoDBPagamentoRepository, pid: str, **kw: Any) -> str:
    pg = repo.obter(pid)
    assert pg is not None
    base = {
        "idEvento": "evt_1",
        "tipo": "PAGAMENTO_APROVADO",
        "idTransacaoExterna": pg.id_transacao_externa,
        "referencia": pid,
        "valorCentavos": 1000,
        "sequencia": 2,
        "ocorridoEm": "2026-10-18T16:00:00.000Z",
    }
    return json.dumps({**base, **kw}, separators=(",", ":"))


def assinado(corpo: str) -> str:
    return assinatura_webhook.assinar(SEGREDO, int(time.time()), corpo)


def test_assinatura_invalida_401(amb: Any) -> None:
    repo, _, pid = amb
    corpo = evento(repo, pid)
    assert chamar(corpo, None)[0] == 401
    assert chamar(corpo, assinatura_webhook.assinar("errado", int(time.time()), corpo))[0] == 401
    antigo = assinatura_webhook.assinar(SEGREDO, int(time.time()) - 1000, corpo)
    assert chamar(corpo, antigo)[0] == 401  # anti-replay


def test_rotacao_do_segredo_aceita_o_atual_e_o_anterior(amb: Any) -> None:
    repo, _, pid = amb
    ssm = boto3.client("ssm")
    ssm.put_parameter(
        Name="/revenda/dev/segredos/webhook-hmac-atual",
        Value="segredo-novo",
        Type="SecureString",
        Overwrite=True,
    )
    modulo._CACHE_SEGREDOS.update(ate=0.0, valores=[])
    corpo = evento(repo, pid)
    assert (
        chamar(corpo, assinatura_webhook.assinar("segredo-novo", int(time.time()), corpo))[0]
        == 200
    )  # novo
    corpo2 = evento(repo, pid, idEvento="evt_9", valorCentavos=1)
    assert (
        chamar(corpo2, assinatura_webhook.assinar(SEGREDO, int(time.time()), corpo2))[0] == 200
    )  # anterior (versao 1)
    assert chamar(corpo2, assinatura_webhook.assinar("outro", int(time.time()), corpo2))[0] == 401


def test_corpo_invalido_400(amb: Any) -> None:
    corpo = '{"x":1}'
    assert chamar(corpo, assinado(corpo))[0] == 400


def test_processa_e_repetido_devolve_a_resposta_original_sem_efeito_duplicado(amb: Any) -> None:
    repo, saga, pid = amb
    corpo = evento(repo, pid)
    assert chamar(corpo, assinado(corpo), "evt_1") == (200, {"resultado": "PROCESSADO"})
    assert chamar(corpo, assinado(corpo), "evt_1") == (200, {"resultado": "PROCESSADO"})
    assert saga.sucessos == ["tok"]  # um unico efeito


def test_valor_divergente_rejeitado_e_idempotency_key_diferente_400(amb: Any) -> None:
    repo, _, pid = amb
    divergente = evento(repo, pid, valorCentavos=1, idEvento="evt_2")
    assert chamar(divergente, assinado(divergente)) == (200, {"resultado": "REJEITADO"})
    ok = evento(repo, pid)
    assert chamar(ok, assinado(ok), "outra-chave")[0] == 400
