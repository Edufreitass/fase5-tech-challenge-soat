"""`transacionar`: repete em TransactionConflict, nao esconde falhas de
condicao."""

from typing import Any

import pytest

from shared.dynamo import transacionar


class Cancelada(Exception):
    def __init__(self, codigos: list[str]) -> None:
        super().__init__("cancelada")
        self.response = {"CancellationReasons": [{"Code": c} for c in codigos]}


class ClienteFake:
    class exceptions:
        TransactionCanceledException = Cancelada

    def __init__(self, falhas: list[list[str]]) -> None:
        self.falhas = list(falhas)
        self.chamadas = 0

    def transact_write_items(self, **_: Any) -> None:
        self.chamadas += 1
        if self.falhas:
            raise Cancelada(self.falhas.pop(0))


def test_repete_ate_a_transacao_concorrente_terminar() -> None:
    cliente = ClienteFake([["TransactionConflict", "None"], ["None", "TransactionConflict"]])
    esperas: list[float] = []
    transacionar(cliente, [], dormir=esperas.append)
    assert cliente.chamadas == 3
    assert len(esperas) == 2
    assert esperas[1] > esperas[0] - 0.05  # backoff crescente (com jitter)


def test_falha_de_condicao_sobe_sem_repetir() -> None:
    cliente = ClienteFake([["ConditionalCheckFailed", "None"]])
    with pytest.raises(Cancelada):
        transacionar(cliente, [], dormir=lambda _: None)
    assert cliente.chamadas == 1


def test_conflito_persistente_sobe_apos_as_tentativas() -> None:
    cliente = ClienteFake([["TransactionConflict"]] * 10)
    with pytest.raises(Cancelada):
        transacionar(cliente, [], tentativas=3, dormir=lambda _: None)
    assert cliente.chamadas == 3
