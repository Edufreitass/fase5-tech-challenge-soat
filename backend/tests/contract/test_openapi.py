"""O backend/contracts/openapi.json versionado deve refletir as rotas
(ATUALIZAR_OPENAPI=1 regenera)."""

import json
import os
from pathlib import Path

from admin.adapters.api.handler import app as app_admin
from api_docs.consolidation import consolidar
from customers.adapters.api.handler import app as app_clientes
from sales.adapters.api.handler import app as app_vendas
from stubs.mock_gateway.adapters.api.handler import app as app_mock
from vehicles.adapters.api.handler import app as app_veiculos

ARQUIVO = Path(__file__).resolve().parents[2] / "contracts" / "openapi.json"


def test_openapi_versionado_esta_atualizado() -> None:
    atual = consolidar([app_admin, app_clientes, app_mock, app_vendas, app_veiculos])
    if os.environ.get("ATUALIZAR_OPENAPI") == "1":
        ARQUIVO.write_text(json.dumps(atual, indent=2, ensure_ascii=False) + "\n")
    assert json.loads(ARQUIVO.read_text()) == atual, (
        "rode ATUALIZAR_OPENAPI=1 pytest backend/tests/contract"
    )
