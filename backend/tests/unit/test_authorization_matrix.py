"""Matriz de autorizacao: 100% das rotas x 4 perfis,
executando o handler de verdade.

A matriz abaixo define o acesso esperado. O teste garante que (1)
toda rota registrada esta na matriz,
(2) toda rota implementada declara exatamente os papeis esperados e (3)
cada perfil recebe 401/403
quando nao tem acesso e nunca 401/403 quando tem (Anti-IDOR por recurso
e coberto nos testes de cada contexto)."""

import json
import re

import pytest
from moto import mock_aws

from admin.adapters.api.handler import app as app_admin
from api_docs.adapters.api.handler import app as app_docs
from customers.adapters.api.handler import app as app_clientes
from payments.adapters.webhook.handler import app as app_webhook
from sales.adapters.api.handler import app as app_vendas
from shared.http import AppRevenda
from stubs.mock_gateway.adapters.api.handler import app as app_mock
from vehicles.adapters.api.handler import app as app_veiculos

TODOS = frozenset({"anonimo", "cliente", "vendedor", "admin"})
STAFF = frozenset({"vendedor", "admin"})
CLIENTE = frozenset({"cliente"})
ADMIN = frozenset({"admin"})
CLIENTE_E_STAFF = frozenset({"cliente", "vendedor", "admin"})

# (metodo, caminho) -> perfis com acesso. SISTEMA/HMAC: autenticados
# fora do JWT (IAM /
# assinatura).
MATRIZ: dict[tuple[str, str], frozenset[str]] = {
    ("GET", "/health"): TODOS,
    ("GET", "/docs"): TODOS,
    ("GET", "/docs/openapi.json"): TODOS,
    ("GET", "/docs/oauth2-redirect"): TODOS,
    ("GET", "/veiculos"): TODOS,
    ("GET", "/veiculos/<id>"): TODOS,
    ("GET", "/veiculos/vendidos"): STAFF,
    ("POST", "/veiculos"): STAFF,
    ("PATCH", "/veiculos/<id>"): STAFF,
    ("POST", "/veiculos/<id>/inativacao"): STAFF,
    ("POST", "/veiculos/<id>/reativacao"): STAFF,
    ("GET", "/gestao/veiculos"): STAFF,
    ("GET", "/gestao/veiculos/<id>"): STAFF,
    ("POST", "/clientes"): CLIENTE,
    ("GET", "/clientes/meu-perfil"): CLIENTE,
    ("PATCH", "/clientes/meu-perfil"): CLIENTE,
    ("POST", "/clientes/meu-perfil/consentimentos"): CLIENTE,
    ("DELETE", "/clientes/meu-perfil"): CLIENTE,
    ("GET", "/clientes/meu-perfil/exportacao"): CLIENTE,
    ("GET", "/clientes/meu-perfil/vendas"): CLIENTE,
    ("POST", "/vendas"): CLIENTE,
    ("GET", "/vendas"): STAFF,
    ("GET", "/vendas/<id>"): CLIENTE_E_STAFF,
    ("POST", "/vendas/<id>/desistencia"): CLIENTE,
    ("GET", "/vendas/<id>/documentacao"): STAFF,
    ("POST", "/vendas/<id>/retirada"): STAFF,
    ("POST", "/webhooks/pagamentos"): TODOS,  # assinatura HMAC, nao JWT
    ("GET", "/configuracao-inicial"): TODOS,
    ("POST", "/configuracao-inicial"): TODOS,
    ("GET", "/administracao/funcionarios"): ADMIN,
    ("POST", "/administracao/funcionarios"): ADMIN,
    ("PATCH", "/administracao/funcionarios/<id>"): ADMIN,
    ("GET", "/administracao/auditoria"): ADMIN,
    ("GET", "/administracao/solicitacoes-lgpd"): ADMIN,
    ("GET", "/administracao/sagas"): ADMIN,
    ("POST", "/administracao/vendas/<id>/fluxo/reprocessamento"): ADMIN,
    ("POST", "/administracao/segredos/webhook/rotacao"): ADMIN,
    ("POST", "/administracao/chaves-pii/rotacao"): ADMIN,
    ("POST", "/_simulacao/pagamentos/cobrancas"): TODOS,  # IAM (SigV4) no API Gateway
    ("POST", "/_simulacao/pagamentos/cobrancas/<id>/cancelar"): TODOS,
    ("POST", "/_simulacao/pagamentos/estornos"): TODOS,
    ("POST", "/_simulacao/pagamentos/cobrancas/<id>/simular"): STAFF,
}

APPS: list[AppRevenda] = [
    app_admin,
    app_clientes,
    app_docs,
    app_mock,
    app_webhook,
    app_vendas,
    app_veiculos,
]
ISS = "https://cognito-idp.us-east-1.amazonaws.com/"


def _normalizar(caminho: str) -> str:
    return re.sub(r"<\w+>", "<id>", caminho)


def _rotas() -> list[tuple[AppRevenda, str, str, tuple[str, ...]]]:
    return [
        (app, m, _normalizar(c), tuple(p.value for p in papeis))
        for app in APPS
        for m, c, papeis in app.rotas
    ]


def _claims(perfil: str) -> dict[str, str] | None:
    base = {"token_use": "access"}
    if perfil == "anonimo":
        return None
    if perfil == "cliente":
        return {**base, "sub": "cli-1", "client_id": "cid-cli", "iss": ISS + "us-east-1_CLI"}
    grupo = "[admin]" if perfil == "admin" else "[vendedor]"
    return {
        **base,
        "sub": f"{perfil}-1",
        "client_id": "cid-func",
        "iss": ISS + "us-east-1_FUNC",
        "cognito:groups": grupo,
    }


def _status(app: AppRevenda, metodo: str, caminho: str, perfil: str) -> int:
    claims = _claims(perfil)
    concreto = re.sub(r"<\w+>", "abc", caminho)
    evento = {
        "httpMethod": metodo,
        "path": concreto,
        "resource": concreto,
        "headers": {},
        "multiValueHeaders": {},
        "queryStringParameters": None,
        "body": json.dumps({}) if metodo in {"POST", "PATCH"} else None,
        "isBase64Encoded": False,
        "requestContext": {
            "authorizer": {"claims": claims} if claims else None,
            "requestId": "r",
            "stage": "v1",
        },
    }
    return int(app.resolve(evento, None)["statusCode"])


def test_toda_rota_registrada_esta_na_matriz_e_vice_versa() -> None:
    registradas = {(m, c) for _, m, c, _ in _rotas()}
    assert registradas - set(MATRIZ) == set(), "rota sem entrada na matriz de autorizacao"
    assert set(MATRIZ) - registradas == set(), "entrada da matriz sem rota implementada"


def _perfis_declarados(papeis: tuple[str, ...]) -> frozenset[str]:
    if papeis in (("anonimo",), ("sistema",)):
        return TODOS
    perfis: set[str] = set()
    if "cliente" in papeis:
        perfis.add("cliente")
    if "vendedor" in papeis:
        perfis |= {"vendedor", "admin"}  # admin herda vendedor
    if "admin" in papeis:
        perfis.add("admin")
    return frozenset(perfis)


@pytest.mark.parametrize(("metodo", "caminho"), sorted(MATRIZ))
def test_papeis_declarados_na_rota_batem_com_a_spec(metodo: str, caminho: str) -> None:
    declarados = [_perfis_declarados(p) for _, m, c, p in _rotas() if (m, c) == (metodo, caminho)]
    assert declarados == [MATRIZ[(metodo, caminho)]]


# O webhook e autenticado por assinatura HMAC (nao por JWT): coberto em
# test_webhook_api.
COM_JWT = sorted(rota for rota in MATRIZ if rota != ("POST", "/webhooks/pagamentos"))


@pytest.mark.parametrize("perfil", sorted(TODOS))
@pytest.mark.parametrize(("metodo", "caminho"), COM_JWT)
def test_cada_perfil_recebe_o_status_de_autorizacao_esperado(
    metodo: str, caminho: str, perfil: str
) -> None:
    app = next(a for a, m, c, _ in _rotas() if (m, c) == (metodo, caminho))
    with mock_aws():
        codigo = _status(app, metodo, caminho, perfil)
    if perfil in MATRIZ[(metodo, caminho)]:
        assert codigo not in {401, 403}, (
            f"{perfil} deveria ter acesso a {metodo} {caminho} (obteve {codigo})"
        )
    else:
        assert codigo == (401 if perfil == "anonimo" else 403), (
            f"{perfil} em {metodo} {caminho}: {codigo}"
        )
