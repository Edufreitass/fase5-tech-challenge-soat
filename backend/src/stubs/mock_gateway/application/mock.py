"""Gateway de pagamento simulado (Pix): cobrancas, estornos e webhooks
assinados."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from shared.errors import RecursoNaoEncontrado
from shared.ids import novo_id
from shared.time import agora_iso


class RepositorioMock(Protocol):
    def obter_cobranca(self, tx: str) -> dict[str, Any] | None: ...

    def salvar_cobranca(self, tx: str, dados: dict[str, Any]) -> bool:
        """False se ja existir (idempotente por referencia)."""
        ...

    def atualizar_status(self, tx: str, de: str, para: str) -> None: ...

    def salvar_estorno(self, estorno_id: str, dados: dict[str, Any]) -> bool: ...

    def obter_estorno(self, estorno_id: str) -> dict[str, Any]: ...


class Fila(Protocol):
    def enviar(self, mensagem: dict[str, Any], atraso_segundos: int) -> None: ...


def _curto(valor: str) -> str:
    return hashlib.sha256(valor.encode()).hexdigest()[:16]


@dataclass
class GatewayMock:
    repositorio: RepositorioMock
    fila: Fila
    relogio: Callable[[], str] = field(default=agora_iso)

    def criar_cobranca(
        self, referencia: str, valor_centavos: int, expira_em: str
    ) -> dict[str, str]:
        tx = f"tx_{_curto(referencia)}"  # deterministico: a saga pode repetir o passo
        pix = (
            f"00020126580014BR.GOV.BCB.PIX0136{tx}"
            f"5204000053039865406{valor_centavos / 100:.2f}5802BR6304ABCD"
        )
        self.repositorio.salvar_cobranca(
            tx,
            {
                "status": "ABERTA",
                "valorCentavos": valor_centavos,
                "referencia": referencia,
                "expiraEm": expira_em,
                "pixCopiaECola": pix,
            },
        )
        existente = self.repositorio.obter_cobranca(tx) or {}
        return {
            "idTransacaoExterna": tx,
            "pixCopiaECola": str(existente.get("pixCopiaECola", pix)),
        }

    def cancelar(self, tx: str) -> None:
        if self.repositorio.obter_cobranca(tx) is None:
            raise RecursoNaoEncontrado("Cobranca inexistente.")
        self.repositorio.atualizar_status(tx, "ABERTA", "CANCELADA")

    def estornar(self, tx: str, valor_centavos: int) -> dict[str, str]:
        cobranca = self.repositorio.obter_cobranca(tx)
        if cobranca is None:
            raise RecursoNaoEncontrado("Cobranca inexistente.")
        estorno_id = f"est_{_curto(tx)}"
        evento = self._evento("ESTORNO_CONCLUIDO", tx, cobranca, 3, f"evt_{estorno_id}_v2")
        self.repositorio.salvar_estorno(
            estorno_id,
            {
                "idTransacaoExterna": tx,
                "valorCentavos": valor_centavos,
                "status": "CONCLUIDO",
                "evento": evento,
            },
        )
        # Reenvia o mesmo payload persistido. Se SQS falhar depois de
        # gravar, o retry recupera a entrega sem duplicar o estorno.
        persistido = self.repositorio.obter_estorno(estorno_id)
        self.fila.enviar(persistido["evento"], 0)
        return {"idEstornoExterno": estorno_id}

    def simular(
        self, tx: str, resultado: str, atraso_segundos: int, *, duplicar: bool, fora_de_ordem: bool
    ) -> int:
        cobranca = self.repositorio.obter_cobranca(tx)
        if cobranca is None:
            raise RecursoNaoEncontrado("Cobranca inexistente.")
        tipo = "PAGAMENTO_APROVADO" if resultado == "APROVADO" else "PAGAMENTO_RECUSADO"
        principal = self._evento(tipo, tx, cobranca, 2, f"evt_{novo_id()}")
        mensagens = [principal]
        if duplicar:
            mensagens.append(principal)  # mesmo idEvento: idempotencia
        if fora_de_ordem:
            contrario = "PAGAMENTO_RECUSADO" if resultado == "APROVADO" else "PAGAMENTO_APROVADO"
            mensagens.append(
                self._evento(contrario, tx, cobranca, 1, f"evt_{novo_id()}")
            )  # chega tarde, seq menor
        for m in mensagens:
            self.fila.enviar(m, atraso_segundos)
        return len(mensagens)

    def _evento(
        self, tipo: str, tx: str, cobranca: dict[str, Any], sequencia: int, id_evento: str
    ) -> dict[str, Any]:
        return {
            "idEvento": id_evento,
            "tipo": tipo,
            "idTransacaoExterna": tx,
            "referencia": cobranca["referencia"],
            "valorCentavos": int(cobranca["valorCentavos"]),
            "sequencia": sequencia,
            "ocorridoEm": self.relogio(),
        }


def corpo_json(evento: dict[str, Any]) -> str:
    return json.dumps(evento, separators=(",", ":"), sort_keys=True)
