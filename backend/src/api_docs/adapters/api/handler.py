"""fn-docs: /health, Swagger UI com Authorize (OAuth2 PKCE) e
openapi.json.
"""

import json
import os
from pathlib import Path
from typing import Any

from aws_lambda_powertools.event_handler import Response

from shared.http import AppRevenda, processar
from shared.security import Papel

app = AppRevenda("api_docs")

OPENAPI = (
    Path(os.environ.get("DADOS_DIR", str(Path(__file__).resolve().parents[3] / "dados")))
    / "openapi.json"
)
VERSAO_SWAGGER = "5.17.14"
CDN = f"https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/{VERSAO_SWAGGER}"


def _esquemas_oauth() -> dict[str, Any]:
    regiao = os.environ.get("AWS_REGION", "us-east-1")
    esquemas: dict[str, Any] = {}
    for chave, prefixo in (("oauthClientes", "CLIENTES"), ("oauthFuncionarios", "FUNCIONARIOS")):
        dominio = os.environ.get(f"DOMINIO_{prefixo}")
        if not dominio:
            continue
        base = f"https://{dominio}.auth.{regiao}.amazoncognito.com/oauth2"
        esquemas[chave] = {
            "type": "oauth2",
            "description": f"Login pelo pool de {prefixo.lower()} (Authorization Code + PKCE).",
            "flows": {
                "authorizationCode": {
                    "authorizationUrl": f"{base}/authorize",
                    "tokenUrl": f"{base}/token",
                    "scopes": {"openid": "Identidade", "email": "E-mail"},
                }
            },
        }
    return esquemas


def especificacao() -> dict[str, Any]:
    """openapi.json versionado + esquemas OAuth2 injetados em tempo de
    execucao."""
    spec: dict[str, Any] = json.loads(OPENAPI.read_text())
    spec["components"]["securitySchemes"].update(_esquemas_oauth())
    return spec


@app.rota("GET", "/health", Papel.ANONIMO, include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok", "versao": os.environ.get("VERSAO_APP", "dev")}


@app.rota("GET", "/docs/openapi.json", Papel.ANONIMO, include_in_schema=False)
def openapi_json() -> dict[str, Any]:
    return especificacao()


def _html_swagger() -> str:
    clientes = os.environ.get("CLIENT_ID_CLIENTES", "")
    funcionarios = os.environ.get("CLIENT_ID_FUNCIONARIOS", "")
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Revenda API</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="{CDN}/swagger-ui.min.css"></head>
<body>
<div style="font:14px sans-serif;padding:8px 16px;background:#f5f5f5">
  Authorize: informe o <b>client_id</b> do pool correspondente.
  Clientes: <code>{clientes}</code> &middot; Funcion&aacute;rios: <code>{funcionarios}</code>
</div>
<div id="swagger-ui"></div>
<script src="{CDN}/swagger-ui-bundle.min.js"></script>
<script>
window.ui = SwaggerUIBundle({{
  url: "docs/openapi.json",
  dom_id: "#swagger-ui",
  oauth2RedirectUrl: location.origin + location.pathname.replace(/\\/docs\\/?$/, "")
    + "/docs/oauth2-redirect",
  persistAuthorization: true,
}});
window.ui.initOAuth({{ usePkceWithAuthorizationCodeGrant: true, scopes: ["openid", "email"] }});
</script></body></html>"""


_REDIRECT = """<!doctype html><html><head><meta
            charset="utf-8"><title>OAuth2</title></head>
            <body><script>
            (function () {
            var oauth2 = window.opener &&
            window.opener.swaggerUIRedirectOauth2;
            if (!oauth2) { document.body.textContent = "Abra pelo
            Swagger UI."; return; }
            var qp = new URLSearchParams(location.search);
            var valido = qp.get("state") === oauth2.state;
            if (qp.get("code")) {
            oauth2.auth.code = qp.get("code");
            oauth2.callback({ auth: oauth2.auth, redirectUrl:
            oauth2.redirectUrl });
            } else if (qp.get("error")) {
            oauth2.errCb({ authId: oauth2.auth.name, source: "auth",
            level: "error",
            message: qp.get("error_description") || qp.get("error")
            });
            }
            if (!valido) {
            oauth2.errCb({ authId: oauth2.auth.name, source: "auth",
            level: "warning",
            message: "State divergente: possivel CSRF." });
            }
            window.close();
            })();
            </script></body></html>
            """


def _html(corpo: str) -> Response[str]:
    return Response(
        status_code=200,
        content_type="text/html; charset=utf-8",
        body=corpo,
        headers={"Cache-Control": "no-store"},
    )


@app.rota("GET", "/docs", Papel.ANONIMO, include_in_schema=False)
def swagger() -> Response[str]:
    return _html(_html_swagger())


@app.rota("GET", "/docs/oauth2-redirect", Papel.ANONIMO, include_in_schema=False)
def redirect_oauth() -> Response[str]:
    return _html(_REDIRECT)


def handler(evento: dict[str, Any], contexto: Any) -> dict[str, Any]:
    return processar(app, evento, contexto)
