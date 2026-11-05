"""Nenhum dado pessoal sintetico (CPF, e-mail, nome, RG) pode aparecer
nos
logs nem no historico da saga.
"""

import re

import pytest
from tests.e2e.conftest import PREFIXO, Ambiente, criar_comprador, salvar

FUNCOES = [
    "fn-clientes-api",
    "fn-clientes-interno",
    "fn-vendas-api",
    "fn-vendas-worker",
    "fn-vendas-outbox",
    "fn-pagamentos-worker",
    "fn-webhook-pagamentos",
    "fn-gateway-mock",
    "fn-veiculos-api",
    "fn-veiculos-worker",
    "fn-admin-api",
    "fn-auditoria",
    "fn-lgpd-worker",
    "fn-migracoes",
    "fn-docs",
]
CPF_FORMATADO = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")


def varrer(ambiente: Ambiente, proibidos: list[str]) -> list[str]:
    logs = ambiente.sessao.client("logs")
    achados: list[str] = []
    grupos = [f"/aws/lambda/{PREFIXO}{f}" for f in FUNCOES] + [
        f"/aws/vendedlogs/states/{PREFIXO}saga-compra"
    ]
    for grupo in grupos:
        token: str | None = None
        while True:
            params = {
                "logGroupName": grupo,
                "limit": 1000,
                **({"nextToken": token} if token else {}),
            }
            try:
                r = logs.filter_log_events(**params)
            except logs.exceptions.ResourceNotFoundException:
                break
            for e in r["events"]:
                if CPF_FORMATADO.search(e["message"]) or any(p in e["message"] for p in proibidos):
                    achados.append(f"{grupo}: {e['message'][:120]}")
            token = r.get("nextToken")
            if not token:
                break
    return achados


@pytest.mark.e2e
def test_logs_sem_dados_pessoais(ambiente: Ambiente) -> None:
    cliente = criar_comprador(
        ambiente, 900
    )  # exercita cadastro e consulta com dados sinteticos conhecidos
    import httpx

    cab = {"Authorization": f"Bearer {cliente['token']}"}
    httpx.get(f"{ambiente.api_url}/clientes/meu-perfil", headers=cab, timeout=30)
    httpx.patch(
        f"{ambiente.api_url}/clientes/meu-perfil",
        headers={**cab, "If-Match": '"v1"'},
        json={"telefone": "+5511911112222"},
        timeout=30,
    )
    achados = varrer(
        ambiente, [*ambiente.cpfs, *ambiente.emails, "Cliente Carga E2E", "12.345.678-9"]
    )
    salvar("pii_em_logs.json", {"grupos_varridos": len(FUNCOES) + 1, "ocorrencias": achados})
    assert achados == [], f"dados pessoais em logs: {achados[:5]}"
