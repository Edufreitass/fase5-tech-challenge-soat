"""infra/config/dev.yml contra o schema e as validacoes."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

RAIZ = Path(__file__).resolve().parents[3]
CONFIG: dict[str, Any] = yaml.safe_load((RAIZ / "infra" / "config" / "dev.yml").read_text())
VALIDADOR = Draft202012Validator(
    json.loads((RAIZ / "infra" / "config" / "schema.json").read_text())
)


def erros(cfg: dict[str, Any]) -> list[str]:
    return [e.message for e in VALIDADOR.iter_errors(cfg)]


def test_config_atual_e_valida() -> None:
    assert erros(CONFIG) == []


def test_soma_de_capacidade_cabe_no_free_tier() -> None:
    capacidade = CONFIG["dynamodb_capacidade"].values()
    assert sum(c["rcu"] for c in capacidade) <= 25
    assert sum(c["wcu"] for c in capacidade) <= 25


@pytest.mark.parametrize(
    ("caminho", "valor"),
    [
        (("regiao",), "sa-east-1"),
        (("destroy",), "sim"),
        (("api", "cors_origens"), ["*"]),
        (("api", "cors_origens"), ["http://inseguro.example"]),
        (("negocio", "prazo_pagamento_segundos"), 30),
        (("negocio", "prazo_retirada_segundos"), 3_000_000),
        (("dynamodb_capacidade", "vendas", "rcu"), 0),
        (("api", "throttling", "webhook_rps"), 0),
        (("observabilidade", "retencao_logs_dias"), 8),
    ],
)
def test_valores_invalidos_sao_reprovados(caminho: tuple[str, ...], valor: Any) -> None:
    cfg = copy.deepcopy(CONFIG)
    alvo = cfg
    for chave in caminho[:-1]:
        alvo = alvo[chave]
    alvo[caminho[-1]] = valor
    assert erros(cfg)


def test_chave_desconhecida_reprovada() -> None:
    assert erros({**CONFIG, "segredo": "x"})
