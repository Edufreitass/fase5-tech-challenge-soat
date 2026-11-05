"""Casos de uso /administracao: auditoria, solicitacoes LGPD,
sagas/redrive e rotacoes.

Toda chamada gera o evento de auditoria `AcaoAdministrativa` (sem dados
pessoais)."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from admin.domain.operations import (
    FiltroAuditoria,
    Sagas,
    Segredos,
    SolicitacoesLgpd,
    TrilhaAuditoria,
)
from admin.domain.ports import PublicadorEventos
from shared.contracts import Cursor
from shared.errors import (
    ErroValidacao,
    RecursoNaoEncontrado,
    RequisicaoInvalida,
    SagaNaoReprocessavel,
)

JANELA_MAXIMA = timedelta(days=31)
STATUS_SAGA_LISTAVEIS = ("FAILED", "RUNNING", "TIMED_OUT")
STATUS_SAGA_REPROCESSAVEIS = ("FAILED", "TIMED_OUT", "ABORTED")
_PERMITIDO = re.compile(r"^[A-Za-z0-9_.:\-]{1,64}$")


def _auditar(eventos: PublicadorEventos, acao: str, ator_id: str, recurso: str) -> None:
    eventos.publicar("AcaoAdministrativa", {"acao": acao, "atorId": ator_id, "recursoId": recurso})


def _valido(nome: str, valor: str | None) -> str | None:
    if valor is None:
        return None
    if not _PERMITIDO.match(
        valor
    ):  # allowlist: o valor vira parte do filter pattern do CloudWatch
        raise RequisicaoInvalida(f"{nome} contem caracteres nao permitidos")
    return valor


@dataclass
class ConsultarAuditoria:
    trilha: TrilhaAuditoria
    eventos: PublicadorEventos

    def executar(  # noqa: PLR0913, PLR0917
        self,
        ator_id: str,
        cliente_id: str | None,
        filtro_ator: str | None,
        acao: str | None,
        de: datetime | None,
        ate: datetime | None,
        limite: int,
        proximo: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        fim = ate or datetime.now(UTC)
        inicio = de or (fim - timedelta(hours=24))
        if inicio >= fim or fim - inicio > JANELA_MAXIMA:
            raise ErroValidacao(
                [{"campo": "de/ate", "mensagem": "janela invalida: de < ate e no maximo 31 dias"}]
            )
        filtro = FiltroAuditoria(
            _valido("clienteId", cliente_id),
            _valido("atorId", filtro_ator),
            _valido("acao", acao),
            inicio,
            fim,
        )
        resultado = self.trilha.buscar(filtro, limite=limite, proximo=proximo)
        _auditar(self.eventos, "CONSULTAR_AUDITORIA", ator_id, "auditoria")
        return resultado


@dataclass
class ListarSolicitacoesLgpd:
    solicitacoes: SolicitacoesLgpd
    eventos: PublicadorEventos

    def executar(
        self, ator_id: str, limite: int, cursor: Cursor | None
    ) -> tuple[list[dict[str, Any]], Cursor | None]:
        resultado = self.solicitacoes.listar(limite=limite, cursor=cursor)
        _auditar(self.eventos, "LISTAR_SOLICITACOES_LGPD", ator_id, "lgpd")
        return resultado


@dataclass
class AdministrarSagas:
    sagas: Sagas
    eventos: PublicadorEventos

    def listar(
        self, ator_id: str, status: str, limite: int, proximo: str | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        if status not in STATUS_SAGA_LISTAVEIS:
            raise ErroValidacao(
                [{"campo": "status", "mensagem": f"use um de {list(STATUS_SAGA_LISTAVEIS)}"}]
            )
        resultado = self.sagas.listar(status, limite=limite, proximo=proximo)
        _auditar(self.eventos, "LISTAR_SAGAS", ator_id, status)
        return resultado

    def reprocessar(self, ator_id: str, venda_id: str) -> None:
        status = self.sagas.status_da_execucao(venda_id)
        if status is None:
            raise RecursoNaoEncontrado("Nao ha execucao da saga para esta venda.")
        if status not in STATUS_SAGA_REPROCESSAVEIS:
            raise SagaNaoReprocessavel(
                f"Execucao em {status}: so FAILED, TIMED_OUT ou ABORTED podem ser reprocessadas."
            )
        self.sagas.reprocessar(venda_id)
        _auditar(self.eventos, "REPROCESSAR_SAGA", ator_id, venda_id)


@dataclass
class RotacionarSegredos:
    segredos: Segredos
    eventos: PublicadorEventos

    def webhook(self, ator_id: str) -> int:
        versao = self.segredos.rotacionar_webhook()
        _auditar(self.eventos, "ROTACIONAR_SEGREDO_WEBHOOK", ator_id, f"v{versao}")
        return versao

    def chave_pii(self, ator_id: str) -> int:
        versao = self.segredos.rotacionar_chave_pii()
        _auditar(self.eventos, "ROTACIONAR_CHAVE_PII", ator_id, f"v{versao}")
        return versao
