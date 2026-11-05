import os

import pytest

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("POWERTOOLS_TRACE_DISABLED", "1")
os.environ.setdefault("POWERTOOLS_SERVICE_NAME", "testes")
os.environ["POOL_FUNCIONARIOS_ID"] = "us-east-1_FUNC"
os.environ["POOL_CLIENTES_ID"] = "us-east-1_CLI"
os.environ["CLIENT_ID_FUNCIONARIOS"] = "cid-func"
os.environ["CLIENT_ID_CLIENTES"] = "cid-cli"
os.environ["SSM_PREFIXO"] = "/revenda/dev"


@pytest.fixture
def claims_admin() -> dict[str, str]:
    return {
        "sub": "admin-1",
        "token_use": "access",
        "client_id": "cid-func",
        "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_FUNC",
        "cognito:groups": "[admin]",
    }


@pytest.fixture
def claims_vendedor(claims_admin: dict[str, str]) -> dict[str, str]:
    return {**claims_admin, "sub": "vend-1", "cognito:groups": "[vendedor]"}


@pytest.fixture
def claims_cliente() -> dict[str, str]:
    return {
        "sub": "cli-1",
        "token_use": "access",
        "client_id": "cid-cli",
        "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_CLI",
    }
