"""Handler /administracao/funcionarios com Cognito simulado (moto)
e eventos de API Gateway REST.
"""

import json
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from moto import mock_aws

from admin.adapters.api import handler as modulo
from admin.adapters.cognito.directory import CognitoDiretorioFuncionarios
from admin.application.employees import AdministrarFuncionarios
from admin.application.setup import ConfigurarPrimeiroAdministrador
from shared import parameters as parametros
from shared.events import PublicadorSns


@pytest.fixture
def ambiente(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    with mock_aws():
        cognito = boto3.client("cognito-idp")
        pool = cognito.create_user_pool(PoolName="func", UsernameAttributes=["email"])["UserPool"][
            "Id"
        ]
        for grupo in ("admin", "vendedor"):
            cognito.create_group(UserPoolId=pool, GroupName=grupo)
        ssm = boto3.client("ssm")
        ssm.put_parameter(Name="/revenda/dev/segredos/cursor-hmac", Value="s3gredo", Type="String")
        casos = AdministrarFuncionarios(
            CognitoDiretorioFuncionarios(cognito, pool), PublicadorSns(boto3.client("sns"), "")
        )
        monkeypatch.setattr(modulo, "_casos_de_uso", lambda: casos)
        parametros.segredo_cursor.cache_clear()
        yield pool


def evento(
    metodo: str,
    caminho: str,
    claims: dict[str, str] | None,
    corpo: Any = None,
    query: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
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
            "requestId": "r1",
            "stage": "v1",
        },
    }


def chamar(*args: Any, **kwargs: Any) -> tuple[int, dict[str, Any], dict[str, Any]]:
    resposta = modulo.handler(evento(*args, **kwargs), None)
    headers = {k: v[0] for k, v in resposta.get("multiValueHeaders", {}).items()}
    return resposta["statusCode"], json.loads(resposta["body"] or "{}"), headers


def test_sem_token_401(ambiente: str) -> None:
    status, corpo, headers = chamar("GET", "/administracao/funcionarios", None)
    assert status == 401
    assert corpo["type"] == "urn:revenda:problema:nao-autenticado"
    assert headers["Content-Type"] == "application/problem+json"
    assert headers["X-Correlation-Id"]
    assert headers["X-Content-Type-Options"] == "nosniff"


def test_vendedor_403(ambiente: str, claims_vendedor: dict[str, str]) -> None:
    assert chamar("GET", "/administracao/funcionarios", claims_vendedor)[0] == 403


def test_cliente_403(ambiente: str, claims_cliente: dict[str, str]) -> None:
    assert chamar("GET", "/administracao/funcionarios", claims_cliente)[0] == 403


def test_ciclo_completo(ambiente: str, claims_admin: dict[str, str]) -> None:
    status, criado, headers = chamar(
        "POST",
        "/administracao/funcionarios",
        claims_admin,
        {"nome": "Vera", "email": "vera@example.com", "grupo": "vendedor"},
    )
    assert status == 201
    assert criado["grupos"] == ["vendedor"]
    assert headers["Location"].endswith(criado["id"])

    status, corpo, _ = chamar(
        "POST",
        "/administracao/funcionarios",
        claims_admin,
        {"nome": "Vera", "email": "vera@example.com", "grupo": "vendedor"},
    )
    assert status == 409
    assert corpo["type"] == "urn:revenda:problema:conflito-unicidade"

    status, listagem, _ = chamar(
        "GET", "/administracao/funcionarios", claims_admin, query={"grupo": "vendedor"}
    )
    assert status == 200
    assert [i["email"] for i in listagem["itens"]] == ["vera@example.com"]

    status, atualizado, _ = chamar(
        "PATCH",
        f"/administracao/funcionarios/{criado['id']}",
        claims_admin,
        {"grupo": "admin", "ativo": False},
    )
    assert status == 200
    assert atualizado["grupos"] == ["admin"]
    assert atualizado["ativo"] is False


def test_validacao_422(ambiente: str, claims_admin: dict[str, str]) -> None:
    status, corpo, _ = chamar(
        "POST",
        "/administracao/funcionarios",
        claims_admin,
        {"nome": "", "email": "invalido", "grupo": "root", "extra": 1},
    )
    assert status == 422
    assert corpo["type"] == "urn:revenda:problema:validacao"
    assert corpo["erros"]


def test_nao_desativar_a_si_mesmo_422(ambiente: str, claims_admin: dict[str, str]) -> None:
    status, criado, _ = chamar(
        "POST",
        "/administracao/funcionarios",
        claims_admin,
        {"nome": "Adm", "email": "adm@example.com", "grupo": "admin"},
    )
    assert status == 201
    proprio = {**claims_admin, "sub": criado["id"]}
    status, corpo, _ = chamar(
        "PATCH", f"/administracao/funcionarios/{criado['id']}", proprio, {"ativo": False}
    )
    assert status == 422
    assert corpo["type"] == "urn:revenda:problema:regra-negocio-violada"


def test_funcionario_inexistente_404(ambiente: str, claims_admin: dict[str, str]) -> None:
    status, corpo, _ = chamar(
        "PATCH", "/administracao/funcionarios/nao-existe", claims_admin, {"ativo": True}
    )
    assert status == 404
    assert corpo["type"] == "urn:revenda:problema:recurso-nao-encontrado"


def test_cursor_invalido_400(ambiente: str, claims_admin: dict[str, str]) -> None:
    status, _, _ = chamar(
        "GET", "/administracao/funcionarios", claims_admin, query={"nextToken": "xx"}
    )
    assert status == 400


@pytest.fixture
def configuracao_inicial(monkeypatch: pytest.MonkeyPatch, ambiente: str) -> None:
    cognito = boto3.client("cognito-idp")
    casos = ConfigurarPrimeiroAdministrador(
        CognitoDiretorioFuncionarios(cognito, ambiente),
        PublicadorSns(boto3.client("sns"), ""),
        lambda: "dono@example.com",
    )
    monkeypatch.setattr(modulo, "_configuracao_inicial", lambda: casos)


def test_configuracao_inicial_convida_so_o_dono_e_so_uma_vez(
    configuracao_inicial: None, ambiente: str
) -> None:
    assert chamar("GET", "/configuracao-inicial", None)[1] == {"necessaria": True}
    status, corpo, _ = chamar("POST", "/configuracao-inicial", None)
    assert status == 201
    assert "dono@example.com" not in json.dumps(corpo)  # a rota e publica: nao vaza o e-mail
    admins = boto3.client("cognito-idp").list_users_in_group(
        UserPoolId=ambiente, GroupName="admin"
    )
    emails = [a["Value"] for u in admins["Users"] for a in u["Attributes"] if a["Name"] == "email"]
    assert emails == ["dono@example.com"]
    assert chamar("GET", "/configuracao-inicial", None)[1] == {"necessaria": False}
    assert chamar("POST", "/configuracao-inicial", None)[0] == 409
