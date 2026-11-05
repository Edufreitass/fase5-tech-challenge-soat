"""Utilitarios de DynamoDB compartilhados pelos adaptadores."""

import random
import time
from collections.abc import Callable
from typing import Any

TENTATIVAS_TRANSACAO = 4


def transacionar(
    cliente: Any,
    itens: list[dict[str, Any]],
    *,
    tentativas: int = TENTATIVAS_TRANSACAO,
    dormir: Callable[[float], None] = time.sleep,
) -> None:
    """`TransactWriteItems` que repete quando outra transacao esta em
    andamento no mesmo item.

    O DynamoDB cancela com `TransactionConflict` (e nao com falha de
    condicao) quando duas
    transacoes disputam o mesmo item ao mesmo tempo; repetir apos um
    instante deixa a condicional
    decidir (uma vence, as demais recebem o 409 de negocio).
    Qualquer outro cancelamento sobe.
    """
    for tentativa in range(tentativas):
        try:
            cliente.transact_write_items(TransactItems=itens)
            return
        except cliente.exceptions.TransactionCanceledException as erro:
            motivos = erro.response.get("CancellationReasons", [])
            ultima = tentativa == tentativas - 1
            if ultima or not any(m.get("Code") == "TransactionConflict" for m in motivos):
                raise
            dormir(0.05 * (2**tentativa) + random.uniform(0, 0.05))  # noqa: S311
