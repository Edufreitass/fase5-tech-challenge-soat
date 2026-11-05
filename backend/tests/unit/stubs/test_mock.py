"""Gateway simulado: cobrancas idempotentes, simulacao (duplicar/fora
de
ordem), estorno e entrega assinada.
"""

import json
import time
from collections.abc import Iterator
from typing import Any

import boto3
import httpx
import pytest
from aws_lambda_powertools.utilities import parameters
from moto import mock_aws

from shared import parameters as parametros
from shared import webhook_signature as assinatura_webhook
from shared.errors import RecursoNaoEncontrado
from stubs.mock_gateway.adapters.api import handler as modulo
from stubs.mock_gateway.adapters.aws import DynamoDBMock
from stubs.mock_gateway.application.mock import GatewayMock
from tests.tables import criar_tabelas


class FilaFake:
    def __init__(self) -> None:
        self.mensagens: list[tuple[dict[str, Any], int]] = []

    def enviar(self, mensagem: dict[str, Any], atraso_segundos: int) -> None:
        self.mensagens.append((mensagem, atraso_segundos))


@pytest.fixture
def mock() -> Iterator[tuple[GatewayMock, FilaFake]]:
    with mock_aws():
        ddb = boto3.client("dynamodb")
        criar_tabelas(ddb)
        fila = FilaFake()
        yield GatewayMock(DynamoDBMock(ddb, "t-mock"), fila), fila


def test_cobranca_idempotente_por_referencia(mock: tuple[GatewayMock, FilaFake]) -> None:
    gw, _ = mock
    a = gw.criar_cobranca("ref-1", 1000, "2026-10-20T00:00:00.000Z")
    b = gw.criar_cobranca("ref-1", 1000, "2026-10-20T00:00:00.000Z")
    assert a == b
    assert a["idTransacaoExterna"].startswith("tx_")
    assert a["pixCopiaECola"].startswith("00020126")
    assert gw.criar_cobranca("ref-2", 1000, "x")["idTransacaoExterna"] != a["idTransacaoExterna"]


def test_simular_aprovado_com_atraso_duplicado_e_fora_de_ordem(
    mock: tuple[GatewayMock, FilaFake],
) -> None:
    gw, fila = mock
    tx = gw.criar_cobranca("ref-1", 1000, "x")["idTransacaoExterna"]
    assert gw.simular(tx, "APROVADO", 30, duplicar=True, fora_de_ordem=True) == 3
    (a, atraso), (b, _), (c, _) = fila.mensagens
    assert atraso == 30
    assert a == b  # mesmo idEvento: o webhook deve ser idempotente
    assert (a["tipo"], a["sequencia"], a["valorCentavos"]) == ("PAGAMENTO_APROVADO", 2, 1000)
    assert (c["tipo"], c["sequencia"]) == ("PAGAMENTO_RECUSADO", 1)
    assert c["idEvento"] != a["idEvento"]


def test_estorno_idempotente_reenvia_mesmo_evento(mock: tuple[GatewayMock, FilaFake]) -> None:
    gw, fila = mock
    tx = gw.criar_cobranca("ref-1", 1000, "x")["idTransacaoExterna"]
    assert gw.estornar(tx, 1000) == gw.estornar(tx, 1000)
    assert [m["tipo"] for m, _ in fila.mensagens] == ["ESTORNO_CONCLUIDO"] * 2
    assert fila.mensagens[0] == fila.mensagens[1]


def test_cobranca_inexistente_404(mock: tuple[GatewayMock, FilaFake]) -> None:
    gw, _ = mock
    for chamada in (
        lambda: gw.cancelar("tx_x"),
        lambda: gw.estornar("tx_x", 1),
        lambda: gw.simular("tx_x", "APROVADO", 0, duplicar=False, fora_de_ordem=False),
    ):
        with pytest.raises(RecursoNaoEncontrado):
            chamada()


def test_cancelar_marca_cobranca(mock: tuple[GatewayMock, FilaFake]) -> None:
    gw, _ = mock
    tx = gw.criar_cobranca("ref-1", 1000, "x")["idTransacaoExterna"]
    gw.cancelar(tx)
    assert gw.repositorio.obter_cobranca(tx)["status"] == "CANCELADA"  # type: ignore[index]


def test_entrega_assina_e_envia_ao_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    with mock_aws():
        boto3.client("ssm").put_parameter(
            Name="/revenda/dev/segredos/webhook-hmac-atual", Value="seg", Type="SecureString"
        )

        parameters.base.DEFAULT_PROVIDERS.clear()  # type: ignore[attr-defined]
        parametros.segredo_cursor.cache_clear()
        monkeypatch.setenv("WEBHOOK_URL", "https://api.exemplo/v1/webhooks/pagamentos")
        recebido: dict[str, Any] = {}

        def responder(req: httpx.Request) -> httpx.Response:
            recebido.update(
                corpo=req.content.decode(),
                sig=req.headers["X-Gateway-Signature"],
                chave=req.headers["Idempotency-Key"],
            )
            return httpx.Response(200)

        evento = {"idEvento": "evt_1", "tipo": "PAGAMENTO_APROVADO", "valorCentavos": 1}
        modulo.entregar_webhook(evento, httpx.Client(transport=httpx.MockTransport(responder)))
        assert recebido["chave"] == "evt_1"
        assert assinatura_webhook.verificar(
            recebido["sig"], recebido["corpo"], ["seg"], int(time.time())
        )
        assert json.loads(recebido["corpo"])["idEvento"] == "evt_1"

        def falhar(_: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        with pytest.raises(httpx.HTTPStatusError):
            modulo.entregar_webhook(evento, httpx.Client(transport=httpx.MockTransport(falhar)))


def test_consumidor_sqs_reporta_falhas_parciais(monkeypatch: pytest.MonkeyPatch) -> None:
    entregues: list[str] = []

    def entregar(evento: dict[str, Any], http: Any = None) -> None:
        if evento["idEvento"] == "ruim":
            raise RuntimeError("falha")
        entregues.append(evento["idEvento"])

    monkeypatch.setattr(modulo, "entregar_webhook", entregar)
    registros = [
        {"messageId": "m1", "eventSource": "aws:sqs", "body": json.dumps({"idEvento": i})}
        for i in ("ok", "ruim")
    ]
    registros[1]["messageId"] = "m2"
    resposta = modulo.handler({"Records": registros}, None)
    assert resposta == {"batchItemFailures": [{"itemIdentifier": "m2"}]}
    assert entregues == ["ok"]


def test_estorno_recupera_falha_de_envio_apos_persistir(
    mock: tuple[GatewayMock, FilaFake], monkeypatch: pytest.MonkeyPatch
) -> None:
    gw, fila = mock
    tx = gw.criar_cobranca("ref-retry", 1000, "x")["idTransacaoExterna"]
    enviar = fila.enviar
    tentadas: list[dict[str, Any]] = []

    def falha(mensagem: dict[str, Any], atraso: int) -> None:
        tentadas.append(mensagem)
        raise TimeoutError("SQS indisponivel")

    monkeypatch.setattr(fila, "enviar", falha)
    with pytest.raises(TimeoutError):
        gw.estornar(tx, 1000)
    monkeypatch.setattr(fila, "enviar", enviar)
    gw.estornar(tx, 1000)
    assert fila.mensagens == [(tentadas[0], 0)]
