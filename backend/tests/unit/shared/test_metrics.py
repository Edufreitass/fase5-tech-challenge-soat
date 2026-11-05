"""Metricas de negocio (EMF) e tratamento de throttling do DynamoDB."""

import json
from typing import Any

import pytest
from botocore.exceptions import ClientError

from shared import metrics as metricas
from shared.http import AppRevenda
from shared.security import Papel


def linhas_emf(saida: str) -> list[dict[str, Any]]:
    return [
        json.loads(linha)
        for linha in saida.splitlines()
        if linha.startswith("{") and "_aws" in linha
    ]


def test_no_maximo_9_metricas_dentro_do_free_tier() -> None:
    assert len(metricas.NOMES) == 9
    assert len(metricas.NOMES) < metricas.LIMITE_FREE_TIER


def test_emitir_gera_linha_emf_no_namespace_e_dimensao_unica(
    capsys: pytest.CaptureFixture[str],
) -> None:
    metricas.emitir(metricas.RESERVAS_CRIADAS)
    emf = linhas_emf(capsys.readouterr().out)[-1]
    diretiva = emf["_aws"]["CloudWatchMetrics"][0]
    assert diretiva["Namespace"] == "Revenda"
    assert diretiva["Dimensions"] == [["service"]]
    assert emf["service"] == "revenda"
    assert emf["ReservasCriadas"] == [1.0]


def test_metrica_desconhecida_e_erro() -> None:
    with pytest.raises(ValueError, match="desconhecida"):
        metricas.emitir("Qualquer")


@pytest.mark.parametrize(
    ("status", "metrica"),
    [
        ("CONCLUIDO", "VendasConcluidas"),
        ("CANCELADO", "VendasCanceladas"),
        ("ESTORNADO", "VendasEstornadas"),
    ],
)
def test_status_final_de_venda(
    status: str, metrica: str, capsys: pytest.CaptureFixture[str]
) -> None:
    metricas.emitir_status_final_de_venda(status)
    assert metrica in linhas_emf(capsys.readouterr().out)[-1]


def test_status_intermediario_nao_emite(capsys: pytest.CaptureFixture[str]) -> None:
    metricas.emitir_status_final_de_venda("PAGO")
    assert linhas_emf(capsys.readouterr().out) == []


def test_cota_do_lambda_vira_503_sem_contar_como_throttling_do_dynamodb(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = AppRevenda("teste-cota")

    @app.rota("GET", "/x", Papel.ANONIMO)
    def x() -> dict[str, str]:
        raise ClientError(
            {"Error": {"Code": "TooManyRequestsException", "Message": "Rate Exceeded"}}, "Invoke"
        )

    evento = {
        "httpMethod": "GET",
        "path": "/x",
        "resource": "/x",
        "headers": {},
        "multiValueHeaders": {},
        "queryStringParameters": None,
        "body": None,
        "isBase64Encoded": False,
        "requestContext": {"requestId": "r", "stage": "v1"},
    }
    resposta = app.resolve(evento, None)
    assert resposta["statusCode"] == 503
    assert resposta["multiValueHeaders"]["Retry-After"] == ["2"]
    assert "DynamoDBThrottling" not in capsys.readouterr().out


def test_throttling_do_dynamodb_vira_503_com_retry_after_e_metrica(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = AppRevenda("teste-throttling")

    @app.rota("GET", "/x", Papel.ANONIMO)
    def x() -> dict[str, str]:
        raise ClientError(
            {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "m"}},
            "PutItem",
        )

    evento = {
        "httpMethod": "GET",
        "path": "/x",
        "resource": "/x",
        "headers": {},
        "multiValueHeaders": {},
        "queryStringParameters": None,
        "body": None,
        "isBase64Encoded": False,
        "requestContext": {"requestId": "r", "stage": "v1"},
    }
    resposta = app.resolve(evento, None)
    corpo = json.loads(resposta["body"])
    assert (resposta["statusCode"], corpo["type"]) == (
        503,
        "urn:revenda:problema:dependencia-indisponivel",
    )
    assert resposta["multiValueHeaders"]["Retry-After"] == ["2"]
    assert "DynamoDBThrottling" in linhas_emf(capsys.readouterr().out)[-1]
