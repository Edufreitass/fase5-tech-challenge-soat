"""Modelos e portas das operacoes administrativas (auditoria, LGPD,
sagas e
rotacoes).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from shared.contracts import Cursor


@dataclass(frozen=True)
class FiltroAuditoria:
    cliente_id: str | None
    ator_id: str | None
    acao: str | None
    de: datetime
    ate: datetime


class TrilhaAuditoria(Protocol):
    def buscar(
        self, filtro: FiltroAuditoria, *, limite: int, proximo: str | None
    ) -> tuple[list[dict[str, Any]], str | None]: ...


class SolicitacoesLgpd(Protocol):
    def listar(
        self, *, limite: int, cursor: Cursor | None
    ) -> tuple[list[dict[str, Any]], Cursor | None]: ...


class Sagas(Protocol):
    def listar(
        self, status: str, *, limite: int, proximo: str | None
    ) -> tuple[list[dict[str, Any]], str | None]: ...

    def status_da_execucao(self, venda_id: str) -> str | None:
        """None se nao existe execucao para a venda."""
        ...

    def reprocessar(self, venda_id: str) -> None: ...


class Segredos(Protocol):
    def rotacionar_webhook(self) -> int:
        """Gera novo segredo HMAC (o anterior continua aceito); retorna
        a versao.
        """
        ...

    def rotacionar_chave_pii(self) -> int:
        """Gera o par `v<n+1>`, publica a chave e dispara a recifragem;
        retorna a nova versao."""
        ...
