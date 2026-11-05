"""Casos de uso do contexto Pagamentos (passos da saga)."""

from collections.abc import Callable
from dataclasses import dataclass, field

from payments.domain.models import Pagamento, StatusPagamento, pagamento_id_da_venda
from payments.domain.ports import ClientesInterno, Gateway, RepositorioPagamentos
from shared.errors import DependenciaIndisponivel, EstadoInvalido
from shared.time import agora_iso, somar_segundos


@dataclass
class EmitirCodigo:
    repositorio: RepositorioPagamentos
    gateway: Gateway
    clientes: ClientesInterno
    relogio: Callable[[], str] = field(default=agora_iso)

    def executar(
        self, venda_id: str, cliente_id: str, valor_centavos: int, prazo_segundos: int
    ) -> dict[str, str]:
        pagamento_id = pagamento_id_da_venda(venda_id)
        existente = self.repositorio.obter(pagamento_id)
        if existente is not None:  # reexecucao do passo: idempotente
            return {"pagamentoId": existente.id, "expiraEm": existente.expira_em}
        agora = self.relogio()
        expira_em = somar_segundos(agora, prazo_segundos)
        pagador = self.clientes.obter_dados_cobranca(cliente_id)  # nao persiste nem loga
        tx, pix = self.gateway.criar_cobranca(
            referencia=pagamento_id,
            valor_centavos=valor_centavos,
            nome=pagador["nomeCompleto"],
            cpf=pagador["cpf"],
            expira_em=expira_em,
        )
        self.repositorio.criar(
            Pagamento(
                id=pagamento_id,
                venda_id=venda_id,
                pix_copia_e_cola=pix,
                valor_centavos=valor_centavos,
                status=StatusPagamento.PENDENTE,
                expira_em=expira_em,
                id_transacao_externa=tx,
                criado_em=agora,
                atualizado_em=agora,
            )
        )
        return {"pagamentoId": pagamento_id, "expiraEm": expira_em}


@dataclass
class CancelarCodigo:
    repositorio: RepositorioPagamentos
    gateway: Gateway
    relogio: Callable[[], str] = field(default=agora_iso)

    def executar(self, pagamento_id: str, motivo: str) -> None:
        pg = self.repositorio.obter(pagamento_id)
        if pg is None:
            return
        if pg.status in (StatusPagamento.APROVADO, StatusPagamento.APROVADO_TARDIO):
            # Pagamento e timeout/desistencia podem competir. Se a
            # aprovacao venceu, compensar o dinheiro antes de liberar.
            Estornar(self.repositorio, self.gateway, self.relogio).executar(pg.id)
            return
        alvo = StatusPagamento.EXPIRADO if motivo == "EXPIRADO" else StatusPagamento.CANCELADO
        if pg.status == StatusPagamento.PENDENTE:
            if not self.repositorio.transicionar(
                pg.id, (StatusPagamento.PENDENTE,), alvo, agora=self.relogio()
            ):
                raise DependenciaIndisponivel("Pagamento mudou; repita a compensacao.")
        elif pg.status not in (StatusPagamento.EXPIRADO, StatusPagamento.CANCELADO):
            return
        # Fecha a janela antes de chamar o gateway. A chamada deve ser
        # idempotente, inclusive em retry apos falha de rede.
        self.gateway.cancelar_cobranca(pg.id_transacao_externa)


@dataclass
class Estornar:
    repositorio: RepositorioPagamentos
    gateway: Gateway
    relogio: Callable[[], str] = field(default=agora_iso)

    def executar(self, pagamento_id: str) -> None:
        pg = self.repositorio.obter(pagamento_id)
        if pg is None:
            raise EstadoInvalido("pagamento inexistente")
        if not pg.requer_estorno():
            return  # ja solicitado/concluido
        id_estorno = self.gateway.estornar(pg.id_transacao_externa, pg.valor_centavos)
        self.repositorio.registrar_estorno(pg.id, id_estorno, self.relogio())
