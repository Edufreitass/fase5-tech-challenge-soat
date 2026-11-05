import json
import os
from pathlib import Path
from typing import Any

import pytest

from api_docs.adapters.api import handler as modulo

RAIZ = Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def dados(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(modulo, "OPENAPI", RAIZ / "backend" / "contracts" / "openapi.json")
    monkeypatch.setenv("DOMINIO_CLIENTES", "revenda-dev-clientes-abc")
    monkeypatch.setenv("DOMINIO_FUNCIONARIOS", "revenda-dev-func-abc")


def chamar(caminho: str) -> dict[str, Any]:
    evento = {
        "httpMethod": "GET",
        "path": caminho,
        "resource": caminho,
        "headers": {},
        "multiValueHeaders": {},
        "queryStringParameters": None,
        "body": None,
        "isBase64Encoded": False,
        "requestContext": {"requestId": "r", "stage": "v1"},
    }
    return modulo.handler(evento, None)


def test_health_publico() -> None:
    resposta = chamar("/health")
    assert resposta["statusCode"] == 200
    assert json.loads(resposta["body"])["status"] == "ok"


def test_openapi_injeta_oauth_dos_dois_pools() -> None:
    resposta = chamar("/docs/openapi.json")
    esquemas = json.loads(resposta["body"])["components"]["securitySchemes"]
    assert {"bearerAuth", "oauthClientes", "oauthFuncionarios"} <= set(esquemas)
    fluxo = esquemas["oauthFuncionarios"]["flows"]["authorizationCode"]
    assert fluxo["authorizationUrl"].endswith("/oauth2/authorize")
    assert "revenda-dev-func-abc" in fluxo["tokenUrl"]


def test_swagger_e_redirect() -> None:
    pagina = chamar("/docs")
    assert pagina["statusCode"] == 200
    assert "usePkceWithAuthorizationCodeGrant" in pagina["body"]
    assert "swagger-ui" in pagina["body"]
    assert "text/html" in pagina["multiValueHeaders"]["Content-Type"][0]
    assert "swaggerUIRedirectOauth2" in chamar("/docs/oauth2-redirect")["body"]


def test_openapi_versionado_nao_contem_dados_da_conta() -> None:
    texto = (RAIZ / "backend" / "contracts" / "openapi.json").read_text()
    assert "amazoncognito" not in texto
    assert "execute-api" not in texto
    assert os.environ.get("AWS_ACCESS_KEY_ID", "x") not in ("", None)
