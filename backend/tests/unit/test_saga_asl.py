"""Estrutura da state machine: referencias, retries,
timeouts
e
compensacoes.
"""

import json
from pathlib import Path
from typing import Any

import pytest

ASL: dict[str, Any] = json.loads(
    (
        Path(__file__).resolve().parents[3] / "infra" / "workflows" / "purchase_saga.asl.json"
    ).read_text()
)
ESTADOS: dict[str, dict[str, Any]] = ASL["States"]


def destinos_do_estado(estado: dict[str, Any]) -> list[str]:
    destinos = [estado.get("Next"), estado.get("Default")]
    destinos += [c["Next"] for c in estado.get("Catch", [])]
    destinos += [c["Next"] for c in estado.get("Choices", [])]
    return [d for d in destinos if d]


def test_todas_as_referencias_existem() -> None:
    assert ASL["StartAt"] in ESTADOS
    for nome, estado in ESTADOS.items():
        destinos = destinos_do_estado(estado)
        for destino in filter(None, destinos):
            assert destino in ESTADOS, f"{nome} -> {destino}"


def test_todo_estado_alcancavel_e_termina() -> None:
    visitados: set[str] = set()
    fila = [ASL["StartAt"]]
    while fila:
        nome = fila.pop()
        if nome in visitados:
            continue
        visitados.add(nome)
        e = ESTADOS[nome]
        fila += destinos_do_estado(e)
    assert visitados == set(ESTADOS)
    finais = {n for n, e in ESTADOS.items() if e["Type"] in {"Succeed", "Fail"}}
    assert finais == {"Concluido", "Cancelado", "Estornado", "FalhaCompensacao"}


def test_esperas_usam_callback_com_timeout_do_input() -> None:
    for nome in ("AguardarPagamento", "AguardarRetirada"):
        e = ESTADOS[nome]
        assert e["Resource"].endswith("lambda:invoke.waitForTaskToken")
        assert e["TimeoutSecondsPath"].startswith("$.prazos.")
        assert e["Parameters"]["Payload"]["taskToken.$"] == "$$.Task.Token"
        # nunca retry em States.Timeout
        assert all(
            "States.Timeout" not in r["ErrorEquals"] and "States.ALL" not in r["ErrorEquals"]
            for r in e["Retry"]
        )


def test_catch_da_espera_de_pagamento_cobre_recusa_desistencia_e_expiracao() -> None:
    erros = {c["ErrorEquals"][0]: c["Next"] for c in ESTADOS["AguardarPagamento"]["Catch"]}
    assert erros == {
        "Pagamento.Recusado": "MotivoRecusado",
        "Venda.Desistencia": "MotivoDesistencia",
        "States.Timeout": "MotivoExpirado",
    }
    erros = {c["ErrorEquals"][0]: c["Next"] for c in ESTADOS["AguardarRetirada"]["Catch"]}
    assert erros == {
        "Venda.Desistencia": "MotivoDesistenciaPosPago",
        "States.Timeout": "ResolverRetirada",
    }


@pytest.mark.parametrize(
    "nome",
    [
        n
        for n, e in ESTADOS.items()
        if e["Type"] == "Task" and "waitForTaskToken" not in e["Resource"]
    ],
)
def test_tasks_tem_retry_com_backoff_e_timeout(nome: str) -> None:
    e = ESTADOS[nome]
    retry = e["Retry"][0]
    assert (
        retry["IntervalSeconds"],
        retry["BackoffRate"],
        retry["MaxAttempts"],
        retry["JitterStrategy"],
    ) == (2, 2, 6, "FULL")
    assert "Erro.Transitorio" in retry["ErrorEquals"]
    assert e.get("TimeoutSeconds")


def test_compensacoes_em_ordem_reversa() -> None:
    def cadeia(inicio: str) -> list[str]:
        nomes, atual = [], inicio
        while ESTADOS[atual]["Type"] != "Succeed":
            nomes.append(atual)
            atual = ESTADOS[atual]["Next"]
        return nomes

    assert cadeia("CancelarCodigoPagamento") == [
        "CancelarCodigoPagamento",
        "LiberarVeiculoCancelamento",
        "CancelarVenda",
        "LiberarLockCancelada",
        "PublicarVendaCancelada",
    ]
    assert cadeia("EstornarPagamento") == [
        "EstornarPagamento",
        "LiberarVeiculoEstorno",
        "EstornarVenda",
        "LiberarLockEstornada",
        "PublicarVendaEstornada",
    ]


def test_input_nao_carrega_dados_pessoais() -> None:
    texto = json.dumps(ESTADOS)
    for proibido in ("cpf", "email", "nomeCompleto", "pixCopiaECola"):
        assert proibido not in texto
