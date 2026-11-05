"""fn-auditoria: SQS -> trilha no log group (formato, sanitizacao e
falhas
parciais).
"""

import json
from collections.abc import Iterator, Mapping

import boto3
import pytest
from moto import mock_aws

from audit.adapters import handler as modulo

GRUPO = "/revenda/dev/auditoria"


@pytest.fixture
def logs(monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    with mock_aws():
        cliente = boto3.client("logs")
        cliente.create_log_group(logGroupName=GRUPO)
        monkeypatch.setenv("AUDITORIA_LOG_GROUP", GRUPO)
        modulo._logs.cache_clear()
        yield cliente


def sqs(*eventos: Mapping[str, object] | str) -> dict[str, object]:
    return {
        "Records": [
            {"messageId": f"m{i}", "body": e if isinstance(e, str) else json.dumps(e)}
            for i, e in enumerate(eventos)
        ]
    }


def test_grava_registro_no_formato_de_auditoria(logs) -> None:  # type: ignore[no-untyped-def]
    evento = {
        "tipo": "AcaoAdministrativa",
        "acao": "CRIAR_FUNCIONARIO",
        "atorId": "adm-1",
        "recursoId": "f-9",
        "ocorridoEm": "2026-10-18T10:00:00.000Z",
        "correlationId": "corr-1",
    }
    assert modulo.handler(sqs(evento), None) == {"batchItemFailures": []}
    eventos = logs.filter_log_events(logGroupName=GRUPO)["events"]
    registro = json.loads(eventos[0]["message"])
    assert (
        registro["quem"],
        registro["acao"],
        registro["recurso"],
        registro["correlationId"],
    ) == (
        "adm-1",
        "CRIAR_FUNCIONARIO",
        "f-9",
        "corr-1",
    )
    assert registro["quando"] == "2026-10-18T10:00:00.000Z"
    assert "recebidoEm" in registro


def test_sanitiza_dados_pessoais_na_justificativa(logs) -> None:  # type: ignore[no-untyped-def]
    evento = {
        "tipo": "DadosPessoaisAcessados",
        "atorId": "v-1",
        "clienteId": "c-1",
        "vendaId": "x",
        "justificativa": "cliente 529.982.247-25 pediu o documento (maria@example.com)",
    }
    modulo.handler(sqs(evento), None)
    texto = logs.filter_log_events(logGroupName=GRUPO)["events"][0]["message"]
    assert "529.982.247-25" not in texto
    assert "maria@example.com" not in texto


def test_evento_invalido_vai_para_falha_parcial_sem_perder_os_validos(logs) -> None:  # type: ignore[no-untyped-def]
    resposta = modulo.handler(
        sqs({"tipo": "ClienteCadastrado", "clienteId": "c"}, "isto nao e json"), None
    )
    assert resposta == {"batchItemFailures": [{"itemIdentifier": "m1"}]}
    assert len(logs.filter_log_events(logGroupName=GRUPO)["events"]) == 1


def test_falha_ao_gravar_devolve_o_lote_inteiro(monkeypatch: pytest.MonkeyPatch) -> None:
    with mock_aws():
        monkeypatch.setenv("AUDITORIA_LOG_GROUP", "/grupo/inexistente")
        modulo._logs.cache_clear()
        resposta = modulo.handler(sqs({"tipo": "X"}, {"tipo": "Y"}), None)
        assert {i["itemIdentifier"] for i in resposta["batchItemFailures"]} == {"m0", "m1"}
