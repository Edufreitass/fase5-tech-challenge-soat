"""Processamento idempotente do webhook do gateway, sem
dependencias de AWS."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from payments.domain.models import Pagamento, Resultado, StatusPagamento, TipoEvento
from payments.domain.ports import RepositorioPagamentos
from shared.errors import DependenciaIndisponivel
from shared.time import agora_iso


@dataclass(frozen=True)
class EventoGateway:
    id_evento: str
    tipo: TipoEvento
    id_transacao_externa: str
    valor_centavos: int
    sequencia: int


class SagaPagamento(Protocol):
    def enviar_sucesso(self, token: str, saida: dict[str, str]) -> bool: ...

    def enviar_falha(self, token: str, erro: str, causa: str) -> bool: ...


class Estorno(Protocol):
    def solicitar_async(self, pagamento_id: str) -> None: ...


class Metricas(Protocol):
    def suspeito(self) -> None: ...

    def pagamento_tardio(self) -> None: ...


@dataclass
class ProcessarEventoGateway:
    repositorio: RepositorioPagamentos
    saga: SagaPagamento
    estorno: Estorno
    metricas: Metricas
    relogio: Callable[[], str] = field(default=agora_iso)

    def executar(self, evento: EventoGateway) -> Resultado:  # noqa: PLR0911
        pg = self.repositorio.por_transacao(evento.id_transacao_externa)
        if pg is None:
            return Resultado.IGNORADO
        if evento.valor_centavos != pg.valor_centavos:
            self.metricas.suspeito()
            return Resultado.REJEITADO
        if evento.sequencia < pg.ultima_sequencia:
            return Resultado.IGNORADO  # fora de ordem
        agora = self.relogio()
        tipo, status = evento.tipo, pg.status

        if tipo == TipoEvento.ESTORNO_CONCLUIDO:
            self.repositorio.concluir_estorno(pg.id, agora)
            return Resultado.PROCESSADO
        if tipo == TipoEvento.PAGAMENTO_APROVADO and status in (
            StatusPagamento.PENDENTE,
            StatusPagamento.APROVADO,
        ):
            return self._notificar(pg, evento, StatusPagamento.APROVADO, agora)
        if tipo == TipoEvento.PAGAMENTO_APROVADO and status in (
            StatusPagamento.EXPIRADO,
            StatusPagamento.CANCELADO,
            StatusPagamento.APROVADO_TARDIO,
        ):
            self._tardio(pg.id, agora)
            return Resultado.PROCESSADO
        if tipo == TipoEvento.PAGAMENTO_RECUSADO and status in (
            StatusPagamento.PENDENTE,
            StatusPagamento.RECUSADO,
        ):
            return self._notificar(pg, evento, StatusPagamento.RECUSADO, agora)
        return Resultado.IGNORADO

    def _notificar(
        self, pg: Pagamento, evento: EventoGateway, alvo: StatusPagamento, agora: str
    ) -> Resultado:
        if pg.status == StatusPagamento.PENDENTE and not self.repositorio.transicionar(
            pg.id,
            (StatusPagamento.PENDENTE,),
            alvo,
            agora=agora,
            sequencia=evento.sequencia,
        ):
            raise DependenciaIndisponivel("Pagamento mudou; repita o evento.")
        # Reentrega recupera falha apos persistir. Token consumido
        # pode significar sucesso; o cancelamento decide sobre estorno.
        if pg.task_token and pg.estorno is None:
            if alvo == StatusPagamento.APROVADO:
                self.saga.enviar_sucesso(pg.task_token, {"resultado": "APROVADO"})
            else:
                self.saga.enviar_falha(pg.task_token, "Pagamento.Recusado", "pagamento recusado")
        return Resultado.PROCESSADO

    def _tardio(self, pagamento_id: str, agora: str) -> None:
        mudou = self.repositorio.transicionar(
            pagamento_id,
            (StatusPagamento.APROVADO, StatusPagamento.EXPIRADO, StatusPagamento.CANCELADO),
            StatusPagamento.APROVADO_TARDIO,
            agora=agora,
        )
        if mudou:
            self.metricas.pagamento_tardio()
        self.estorno.solicitar_async(pagamento_id)
