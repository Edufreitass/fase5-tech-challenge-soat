"""Passos da saga no contexto Vendas: outbox, registro de tokens,
transicoes e varredura."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sales.domain.models import Ator, MotivoCancelamento, StatusVenda, Venda
from sales.domain.ports import CicloVenda, Saga
from shared.contracts import EntradaSaga
from shared.time import agora_iso, somar_segundos

LIMITE_RESERVADO_SEM_SAGA = timedelta(minutes=10)
LIMITE_CRIADO = timedelta(minutes=5)
CAMPOS_TOKEN = ("taskToken", "etapaEspera")


class Prazos(Protocol):
    def pagamento_segundos(self) -> int: ...

    def retirada_segundos(self) -> int: ...


class TokensPagamento(Protocol):
    def registrar_token(self, pagamento_id: str, token: str) -> None: ...

    def status(self, pagamento_id: str) -> str | None: ...


def montar_entrada(venda: Venda, prazos: Prazos) -> EntradaSaga:
    """Entrada sem documentos ou contatos; IDs continuam vinculaveis."""
    return {
        "vendaId": venda.id,
        "veiculoId": venda.veiculo_id,
        "clienteId": venda.cliente_id,
        "valorCentavos": venda.preco_negociado_centavos,
        "correlationId": venda.correlation_id,
        "prazos": {
            "pagamentoSegundos": prazos.pagamento_segundos(),
            "retiradaSegundos": prazos.retirada_segundos(),
        },
    }


@dataclass
class IniciarSaga:
    vendas: CicloVenda
    saga: Saga
    prazos: Prazos

    def executar(self, venda: Venda) -> str:
        arn = self.saga.iniciar(montar_entrada(venda, self.prazos), nome=venda.id)
        self.vendas.definir_saga(venda.id, arn)
        return arn


@dataclass
class PassosVenda:
    vendas: CicloVenda
    saga: Saga
    pagamentos: TokensPagamento
    relogio: Callable[[], str] = field(default=agora_iso)

    def registrar_token(
        self, etapa: str, venda_id: str, token: str, pagamento_id: str | None
    ) -> None:
        if not self.vendas.registrar_token(venda_id, etapa, token):
            self.saga.enviar_falha(
                token, "Venda.Desistencia", "desistencia solicitada antes da espera"
            )
            return
        if etapa == "PAGAMENTO" and pagamento_id:
            self.pagamentos.registrar_token(pagamento_id, token)
            # o webhook pode ter chegado antes do token: resolve a
            # espera agora
            status = self.pagamentos.status(pagamento_id)
            if status == "APROVADO":
                self.saga.enviar_sucesso(token, {"resultado": "APROVADO"})
            elif status == "RECUSADO":
                self.saga.enviar_falha(token, "Pagamento.Recusado", "pagamento recusado")

    def atualizar_venda(  # noqa: PLR0913
        self,
        venda_id: str,
        de: str,
        para: str,
        *,
        motivo: str | None,
        ator: str,
        definir: dict[str, Any],
        prazo_retirada_segundos: int | None,
    ) -> None:
        agora = self.relogio()
        alvo = StatusVenda(para)
        extras = dict(definir)
        if alvo == StatusVenda.PAGO and prazo_retirada_segundos:
            extras["retiradaLimiteEm"] = somar_segundos(agora, prazo_retirada_segundos)
        self.vendas.transicionar(
            venda_id,
            StatusVenda(de),
            alvo,
            agora=agora,
            ator=Ator(ator),
            motivo=MotivoCancelamento(motivo) if motivo else None,
            definir=extras,
            remover=CAMPOS_TOKEN,
        )

    def liberar_lock(self, cliente_id: str, venda_id: str) -> None:
        self.vendas.liberar_lock(cliente_id, venda_id)


@dataclass
class Varredura:
    """Inicia sagas orfas e cancela CRIADO antigas."""

    vendas: CicloVenda
    iniciar: IniciarSaga
    relogio: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))

    @staticmethod
    def _iso(momento: datetime) -> str:
        return momento.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def executar(self) -> dict[str, int]:
        agora = self.relogio()
        iniciadas = 0
        for venda in self.vendas.pendentes_de_saga(self._iso(agora - LIMITE_RESERVADO_SEM_SAGA)):
            self.iniciar.executar(venda)
            iniciadas += 1
        canceladas = 0
        for venda in self.vendas.criados_antigos(self._iso(agora - LIMITE_CRIADO)):
            self.vendas.transicionar(
                venda.id,
                StatusVenda.CRIADO,
                StatusVenda.CANCELADO,
                agora=self._iso(agora),
                ator=Ator.SISTEMA,
                motivo=MotivoCancelamento.FALHA_SISTEMICA,
            )
            canceladas += 1
        return {"sagasIniciadas": iniciadas, "criadasCanceladas": canceladas}
