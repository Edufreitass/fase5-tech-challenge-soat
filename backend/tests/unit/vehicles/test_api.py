"""API de veiculos com DynamoDB simulado (moto): cadastro, unicidade,
listagem ordenada e paginada."""

import json
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from moto import mock_aws

from shared import parameters as parametros
from vehicles.adapters.api import handler as modulo
from vehicles.adapters.dynamodb.repository import DynamoDBVeiculoRepository
from vehicles.application.registration import CadastrarVeiculo
from vehicles.domain.models import NovoVeiculo, StatusVeiculo
from vehicles.domain.validation import digito_renavam


def renavam(n: int) -> str:
    base = f"{n:010d}"
    return base + str(digito_renavam(base))


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch) -> Iterator[DynamoDBVeiculoRepository]:
    with mock_aws():
        ddb = boto3.client("dynamodb")
        ddb.create_table(
            TableName="t-veiculos",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": a, "AttributeType": "S"}
                for a in ("pk", "sk", "gsi1pk", "gsi1sk")
            ],
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "gsi_status_preco",
                    "KeySchema": [
                        {"AttributeName": "gsi1pk", "KeyType": "HASH"},
                        {"AttributeName": "gsi1sk", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        )
        boto3.client("ssm").put_parameter(
            Name="/revenda/dev/segredos/cursor-hmac", Value="s3gredo", Type="String"
        )
        parametros.segredo_cursor.cache_clear()
        r = DynamoDBVeiculoRepository(ddb, "t-veiculos")
        monkeypatch.setattr(modulo, "_repositorio", lambda: r)
        yield r


def cadastrar(repo: DynamoDBVeiculoRepository, n: int, preco: str, **kw: Any) -> str:
    novo = NovoVeiculo(
        marca="Fiat",
        modelo=f"Modelo {n}",
        ano_fabricacao=2022,
        ano_modelo=2022,
        cor="Branco",
        preco=preco,
        quilometragem=10,
        renavam=renavam(n),
        chassi=f"9BXDMK{n:011d}",
        placa=kw.get("placa"),
    )
    return CadastrarVeiculo(repo).executar(novo, "teste").id


def chamar(
    metodo: str,
    caminho: str,
    claims: dict[str, str] | None = None,
    corpo: Any = None,
    query: dict[str, str] | None = None,
) -> tuple[int, Any, dict[str, str]]:
    evento = {
        "httpMethod": metodo,
        "path": caminho,
        "resource": caminho,
        "headers": {},
        "multiValueHeaders": {},
        "queryStringParameters": query,
        "multiValueQueryStringParameters": {k: [v] for k, v in (query or {}).items()} or None,
        "body": json.dumps(corpo) if corpo is not None else None,
        "isBase64Encoded": False,
        "requestContext": {
            "authorizer": {"claims": claims} if claims else None,
            "requestId": "r",
            "stage": "v1",
        },
    }
    r = modulo.handler(evento, None)
    headers = {k: v[0] for k, v in r.get("multiValueHeaders", {}).items()}
    return r["statusCode"], json.loads(r["body"] or "{}"), headers


CORPO = {
    "marca": "Volkswagen",
    "modelo": "T-Cross",
    "anoFabricacao": 2023,
    "anoModelo": 2024,
    "cor": "Cinza",
    "preco": "129900.00",
    "quilometragem": 18500,
    "placa": "BRA2E19",
    "renavam": renavam(123),
    "chassi": "9BWZZZ377VT004251",
    "combustivel": "FLEX",
    "cambio": "AUTOMATICO",
}


def test_cadastro_exige_funcionario(repo, claims_cliente) -> None:  # type: ignore[no-untyped-def]
    assert chamar("POST", "/veiculos", None, CORPO)[0] == 401
    assert chamar("POST", "/veiculos", claims_cliente, CORPO)[0] == 403


def test_cadastro_ok_e_unicidade(repo, claims_vendedor) -> None:  # type: ignore[no-untyped-def]
    status, corpo, headers = chamar("POST", "/veiculos", claims_vendedor, CORPO)
    assert status == 201
    assert corpo["status"] == "DISPONIVEL"
    assert corpo["versao"] == 1
    assert headers["ETag"] == '"v1"'
    assert headers["Location"].endswith(corpo["id"])
    assert corpo["renavam"] == CORPO["renavam"]  # visao interna do funcionario
    status, erro, _ = chamar("POST", "/veiculos", claims_vendedor, CORPO)
    assert status == 409
    assert erro["type"] == "urn:revenda:problema:conflito-unicidade"
    outro = {**CORPO, "chassi": "9BWZZZ377VT004252", "renavam": renavam(124)}
    assert chamar("POST", "/veiculos", claims_vendedor, outro)[0] == 409  # placa repetida


def test_validacao_422(repo, claims_vendedor) -> None:  # type: ignore[no-untyped-def]
    status, erro, _ = chamar(
        "POST", "/veiculos", claims_vendedor, {**CORPO, "renavam": "12345678901"}
    )
    assert status == 422
    assert erro["erros"][0]["campo"] == "renavam"
    assert chamar("POST", "/veiculos", claims_vendedor, {**CORPO, "extra": 1})[0] == 422


def test_listagem_publica_ordenada_e_paginada(repo) -> None:  # type: ignore[no-untyped-def]
    for n, preco in enumerate(
        ["90000.00", "5000.00", "70000.50", "70000.49", "120000.00"], start=1
    ):
        cadastrar(repo, n, preco)
    primeira, tudo = None, []
    token = None
    while True:
        query = {"limit": "2", **({"nextToken": token} if token else {})}
        status, corpo, headers = chamar("GET", "/veiculos", query=query)
        assert status == 200
        assert headers["Cache-Control"] == "public, max-age=30"
        primeira = primeira or corpo
        tudo += [i["preco"] for i in corpo["itens"]]
        token = corpo["nextToken"]
        if not token:
            break
    assert len(primeira["itens"]) == 2
    assert tudo == ["5000.00", "70000.49", "70000.50", "90000.00", "120000.00"]


def test_listagem_oculta_dados_internos(repo) -> None:  # type: ignore[no-untyped-def]
    cadastrar(repo, 1, "1000.00", placa="BRA2E19")
    item = chamar("GET", "/veiculos")[1]["itens"][0]
    assert item["placa"] == "BRA****"
    assert "renavam" not in item
    assert "chassi" not in item


def test_listagem_so_disponiveis_e_parametros(repo) -> None:  # type: ignore[no-untyped-def]
    assert chamar("GET", "/veiculos")[1] == {"itens": [], "nextToken": None}
    assert chamar("GET", "/veiculos", query={"ordenar": "preco_desc"})[0] == 400
    assert chamar("GET", "/veiculos", query={"status": "VENDIDO"})[0] == 400
    assert chamar("GET", "/veiculos", query={"limit": "99"})[0] == 400
    assert chamar("GET", "/veiculos", query={"nextToken": "lixo"})[0] == 400


def test_detalhe(repo) -> None:  # type: ignore[no-untyped-def]
    vid = cadastrar(repo, 1, "1000.00", placa="BRA2E19")
    status, corpo, headers = chamar("GET", f"/veiculos/{vid}")
    assert status == 200
    assert corpo["placa"] == "BRA****"
    assert "renavam" not in corpo
    assert headers["ETag"] == '"v1"'
    assert chamar("GET", "/veiculos/nao-existe")[0] == 404
    assert chamar("GET", "/veiculos/" + "x" * 40)[0] == 404


def test_detalhe_inativo_404(repo) -> None:  # type: ignore[no-untyped-def]
    vid = cadastrar(repo, 1, "1000.00")
    repo._ddb.update_item(
        TableName="t-veiculos",
        Key={"pk": {"S": f"VEICULO#{vid}"}, "sk": {"S": "META"}},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": {"S": StatusVeiculo.INATIVO.value}},
    )
    assert chamar("GET", f"/veiculos/{vid}")[0] == 404
