"""Clientes: PATCH /clientes/meu-perfil (If-Match), consentimentos e
pendencias pelo termo vigente."""

import json
from typing import Any

import boto3
import pytest
from aws_lambda_powertools.utilities import parameters

from customers.adapters.api import handler as modulo
from tests.unit.customers.test_api import CORPO, Ambiente, amb, chamar  # noqa: F401


class SemCompras:
    def possui(self, cliente_id: str) -> bool:
        return False


@pytest.fixture(autouse=True)
def sem_compras(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(modulo, "_vendas_em_andamento", SemCompras)


def req(
    metodo: str, caminho: str, claims: dict[str, str], corpo: Any = None, versao: str | None = None
) -> tuple[int, Any, dict[str, str]]:
    evento = {
        "httpMethod": metodo,
        "path": caminho,
        "resource": caminho,
        "headers": {"User-Agent": "pytest", **({"If-Match": versao} if versao else {})},
        "multiValueHeaders": {},
        "queryStringParameters": None,
        "body": json.dumps(corpo) if corpo is not None else None,
        "isBase64Encoded": False,
        "requestContext": {
            "authorizer": {"claims": claims},
            "requestId": "r",
            "stage": "v1",
            "identity": {"sourceIp": "203.0.113.9"},
        },
    }
    r = modulo.handler(evento, None)
    return (
        r["statusCode"],
        json.loads(r["body"] or "{}"),
        {k: v[0] for k, v in r.get("multiValueHeaders", {}).items()},
    )


def cadastrado(amb: Ambiente, email: str = "maria@example.com", **extra: Any) -> dict[str, str]:
    claims = amb.usuario(email)
    assert chamar("POST", "/clientes", claims, {**CORPO, **extra})[0] == 201
    return claims


def test_patch_exige_if_match(amb: Ambiente) -> None:
    claims = cadastrado(amb)
    assert req("PATCH", "/clientes/meu-perfil", claims, {"telefone": "+5511999990000"})[0] == 428
    assert (
        req("PATCH", "/clientes/meu-perfil", claims, {"telefone": "+5511999990000"}, "lixo")[0]
        == 400
    )
    status, erro, _ = req(
        "PATCH", "/clientes/meu-perfil", claims, {"telefone": "+5511999990000"}, '"v7"'
    )
    assert (status, erro["type"]) == (412, "urn:revenda:problema:versao-desatualizada")


def test_patch_atualiza_mascara_e_versiona(amb: Ambiente) -> None:
    claims = cadastrado(amb)
    status, corpo, headers = req(
        "PATCH",
        "/clientes/meu-perfil",
        claims,
        {
            "nomeCompleto": "Maria S. Lima",
            "telefone": "+5511999990000",
            "cnh": "12345678901",
            "endereco": {**CORPO["endereco"], "numero": "2000"},
        },
        '"v1"',
    )
    assert status == 200
    assert (corpo["nomeCompleto"], corpo["telefone"], corpo["endereco"]["numero"]) == (
        "Maria S. Lima",
        "+5511999990000",
        "2000",
    )
    assert corpo["cnh"] == "*******8901"
    assert corpo["cpf"] == "***.***.247-25"  # CPF nunca muda nem aparece
    assert headers["ETag"] == '"v2"'
    assert "12345678901" not in json.dumps(
        amb.ddb.scan(TableName="t-clientes")["Items"]
    )  # CNH so cifrada
    assert (
        req("PATCH", "/clientes/meu-perfil", claims, {"telefone": "+5511888880000"}, '"v1"')[0]
        == 412
    )  # versao consumida
    status, corpo, headers = chamar("GET", "/clientes/meu-perfil", claims)
    assert (corpo["cnh"], headers["ETag"]) == ("*******8901", '"v2"')


def test_patch_nao_aceita_cpf_nem_email_e_valida_campos(amb: Ambiente) -> None:
    claims = cadastrado(amb)
    assert req("PATCH", "/clientes/meu-perfil", claims, {"cpf": "11144477735"}, '"v1"')[0] == 422
    assert req("PATCH", "/clientes/meu-perfil", claims, {"email": "x@y.com"}, '"v1"')[0] == 422
    status, erro, _ = req(
        "PATCH", "/clientes/meu-perfil", claims, {"telefone": "123", "cnh": "1"}, '"v1"'
    )
    assert status == 422
    assert {e["campo"] for e in erro["erros"]} == {"telefone", "cnh"}


def test_patch_sem_mudanca_nao_gera_nova_versao(amb: Ambiente) -> None:
    claims = cadastrado(amb)
    status, corpo, headers = req(
        "PATCH", "/clientes/meu-perfil", claims, {"telefone": "+5511987654321"}, '"v1"'
    )
    assert (status, headers["ETag"]) == (200, '"v1"')


def test_endereco_e_rg_bloqueados_com_compra_em_andamento(amb: Ambiente, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    claims = cadastrado(amb)
    amb.ddb.create_table(
        TableName="t-vendas",
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": a, "AttributeType": "S"} for a in ("pk", "sk")],
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
    )
    from customers.adapters.dynamodb.sales import VendasEmAndamentoDynamo

    monkeypatch.setattr(
        modulo, "_vendas_em_andamento", lambda: VendasEmAndamentoDynamo(amb.ddb, "t-vendas")
    )
    amb.ddb.put_item(
        TableName="t-vendas",
        Item={
            "pk": {"S": f"CLIENTE#{claims['sub']}"},
            "sk": {"S": "RESERVA_ATIVA"},
            "vendaId": {"S": "v"},
        },
    )
    for corpo in ({"endereco": CORPO["endereco"]}, {"rg": CORPO["rg"]}):
        status, erro, _ = req("PATCH", "/clientes/meu-perfil", claims, corpo, '"v1"')
        assert (status, erro["type"]) == (422, "urn:revenda:problema:regra-negocio-violada")
    assert (
        req("PATCH", "/clientes/meu-perfil", claims, {"telefone": "+5511999990000"}, '"v1"')[0]
        == 200
    )  # telefone pode


def test_incluir_rg_completa_o_cadastro(amb: Ambiente) -> None:
    claims = amb.usuario("maria@example.com")
    sem_rg = {k: v for k, v in CORPO.items() if k != "rg"}
    assert chamar("POST", "/clientes", claims, sem_rg)[1]["camposPendentes"] == ["rg"]
    status, corpo, _ = req("PATCH", "/clientes/meu-perfil", claims, {"rg": CORPO["rg"]}, '"v1"')
    assert (status, corpo["cadastroCompleto"], corpo["rg"]["numero"]) == (
        200,
        True,
        "**.***.678-9",
    )


def test_consentimentos_marketing_e_regras(amb: Ambiente) -> None:
    claims = cadastrado(amb)
    ok = {"versaoTermo": "2026-10-v1", "aceito": True, "finalidades": ["MARKETING"]}
    status, corpo, _ = req("POST", "/clientes/meu-perfil/consentimentos", claims, ok)
    assert (status, corpo["aceito"], corpo["finalidades"]) == (201, True, ["MARKETING"])
    assert (
        req("POST", "/clientes/meu-perfil/consentimentos", claims, {**ok, "aceito": False})[0]
        == 201
    )  # revogacao de MARKETING
    assert (
        req(
            "POST",
            "/clientes/meu-perfil/consentimentos",
            claims,
            {**ok, "finalidades": ["EXECUCAO_CONTRATO"], "aceito": False},
        )[0]
        == 422
    )
    assert (
        req(
            "POST",
            "/clientes/meu-perfil/consentimentos",
            claims,
            {**ok, "versaoTermo": "1999-01-v1"},
        )[0]
        == 422
    )
    assert (
        req("POST", "/clientes/meu-perfil/consentimentos", claims, {**ok, "finalidades": []})[0]
        == 422
    )
    historico = [
        i
        for i in amb.ddb.scan(TableName="t-clientes")["Items"]
        if i["sk"]["S"].startswith("CONSENTIMENTO#")
    ]
    assert len(historico) == 3  # cadastro + aceite + revogacao (append-only)
    assert "203.0.113.9" not in json.dumps(historico)  # IP so como HMAC


def test_novo_termo_gera_pendencia_ate_novo_aceite(amb: Ambiente) -> None:
    claims = cadastrado(amb)
    assert chamar("GET", "/clientes/meu-perfil", claims)[1]["camposPendentes"] == []
    boto3.client("ssm").put_parameter(
        Name="/revenda/dev/params/versao-termo-vigente",
        Value="2027-01-v2",
        Type="String",
        Overwrite=True,
    )
    parameters.base.DEFAULT_PROVIDERS.clear()  # type: ignore[attr-defined]
    corpo = chamar("GET", "/clientes/meu-perfil", claims)[1]
    assert (corpo["cadastroCompleto"], corpo["camposPendentes"]) == (False, ["consentimento"])
    status, resp, _ = req(
        "POST",
        "/clientes/meu-perfil/consentimentos",
        claims,
        {"versaoTermo": "2027-01-v2", "aceito": True, "finalidades": ["EXECUCAO_CONTRATO"]},
    )
    assert (status, resp["cadastroCompleto"], resp["consentimentoVigente"]["versaoTermo"]) == (
        201,
        True,
        "2027-01-v2",
    )
    assert chamar("GET", "/clientes/meu-perfil", claims)[1]["cadastroCompleto"] is True
