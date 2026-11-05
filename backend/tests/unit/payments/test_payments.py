"""Emissao/cancelamento/estorno do pagamento, processamento do webhook
(duplicado, fora de ordem, tardio) e assinatura.
"""

import json
import time
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from moto import mock_aws

from payments.adapters.dynamodb.repository import DynamoDBPagamentoRepository
from payments.application.payment import CancelarCodigo, EmitirCodigo, Estornar
from payments.application.webhook import EventoGateway, ProcessarEventoGateway
from payments.domain.models import Resultado, StatusPagamento, TipoEvento, pagamento_id_da_venda
from shared import webhook_signature as assinatura_webhook
from shared.errors import EstadoInvalido
from tests.tables import criar_tabelas


class GatewayFake:
    def __init__(self) -> None:
        self.criadas = 0
        self.canceladas: list[str] = []
        self.estornos: list[str] = []

    def criar_cobranca(
        self, *, referencia: str, valor_centavos: int, nome: str, cpf: str, expira_em: str
    ) -> tuple[str, str]:
        self.criadas += 1
        return f"tx_{referencia[:8]}", "000201...6304ABCD"

    def cancelar_cobranca(self, id_transacao_externa: str) -> None:
        self.canceladas.append(id_transacao_externa)

    def estornar(self, id_transacao_externa: str, valor_centavos: int) -> str:
        self.estornos.append(id_transacao_externa)
        return "est_1"


class ClientesFake:
    def obter_dados_cobranca(self, cliente_id: str) -> dict[str, str]:
        return {"nomeCompleto": "Maria", "cpf": "52998224725"}


class SagaFake:
    def __init__(self) -> None:
        self.sucessos: list[str] = []
        self.falhas: list[tuple[str, str]] = []
        self.consumido = False

    def enviar_sucesso(self, token: str, saida: dict[str, str]) -> bool:
        self.sucessos.append(token)
        return not self.consumido

    def enviar_falha(self, token: str, erro: str, causa: str) -> bool:
        self.falhas.append((token, erro))
        return True


class EstornoFake:
    def __init__(self) -> None:
        self.pedidos: list[str] = []

    def solicitar_async(self, pagamento_id: str) -> None:
        self.pedidos.append(pagamento_id)


class MetricasFake:
    suspeitos = 0
    tardios = 0

    def suspeito(self) -> None:
        self.suspeitos += 1

    def pagamento_tardio(self) -> None:
        self.tardios += 1


class Ctx:
    def __init__(self) -> None:
        ddb = boto3.client("dynamodb")
        criar_tabelas(ddb)
        self.repo = DynamoDBPagamentoRepository(ddb, "t-pagamentos")
        self.gateway = GatewayFake()
        self.saga = SagaFake()
        self.estorno = EstornoFake()
        self.metricas = MetricasFake()
        self.processar = ProcessarEventoGateway(self.repo, self.saga, self.estorno, self.metricas)

    def emitir(self, venda: str = "venda-1") -> str:
        r = EmitirCodigo(self.repo, self.gateway, ClientesFake()).executar(
            venda, "cli", 12_990_000, 172800
        )
        return r["pagamentoId"]

    def evento(
        self, tipo: TipoEvento, pg_id: str, seq: int = 2, valor: int = 12_990_000, eid: str = "e1"
    ) -> EventoGateway:
        pg = self.repo.obter(pg_id)
        assert pg is not None
        return EventoGateway(eid, tipo, pg.id_transacao_externa, valor, seq)


@pytest.fixture
def ctx() -> Iterator[Ctx]:
    with mock_aws():
        yield Ctx()


def test_emitir_codigo_e_idempotente(ctx: Ctx) -> None:
    a, b = ctx.emitir(), ctx.emitir()
    assert a == b == pagamento_id_da_venda("venda-1")
    assert ctx.gateway.criadas == 1
    pg = ctx.repo.obter(a)
    assert pg is not None
    assert pg.status == StatusPagamento.PENDENTE
    assert ctx.repo.por_transacao(pg.id_transacao_externa) == pg


def test_aprovado_duplicado_repete_callback_sem_alterar_pagamento(ctx: Ctx) -> None:
    pid = ctx.emitir()
    ctx.repo.registrar_token(pid, "tok")
    assert (
        ctx.processar.executar(ctx.evento(TipoEvento.PAGAMENTO_APROVADO, pid))
        == Resultado.PROCESSADO
    )
    assert (
        ctx.processar.executar(ctx.evento(TipoEvento.PAGAMENTO_APROVADO, pid, eid="e2"))
        == Resultado.PROCESSADO
    )
    assert ctx.saga.sucessos == ["tok", "tok"]
    pg = ctx.repo.obter(pid)
    assert pg is not None
    assert pg.status == StatusPagamento.APROVADO


def test_recusado_envia_falha(ctx: Ctx) -> None:
    pid = ctx.emitir()
    ctx.repo.registrar_token(pid, "tok")
    assert (
        ctx.processar.executar(ctx.evento(TipoEvento.PAGAMENTO_RECUSADO, pid))
        == Resultado.PROCESSADO
    )
    assert ctx.saga.falhas == [("tok", "Pagamento.Recusado")]


def test_fora_de_ordem_e_ignorado(ctx: Ctx) -> None:
    pid = ctx.emitir()
    ctx.repo.registrar_token(pid, "tok")
    ctx.processar.executar(ctx.evento(TipoEvento.PAGAMENTO_APROVADO, pid, seq=2))
    # o RECUSADO antigo (seq 1) chega depois: nao desfaz a aprovacao
    assert (
        ctx.processar.executar(ctx.evento(TipoEvento.PAGAMENTO_RECUSADO, pid, seq=1, eid="e0"))
        == Resultado.IGNORADO
    )
    pg = ctx.repo.obter(pid)
    assert pg is not None
    assert pg.status == StatusPagamento.APROVADO
    assert ctx.saga.falhas == []


def test_valor_divergente_e_rejeitado_e_transacao_desconhecida_ignorada(ctx: Ctx) -> None:
    pid = ctx.emitir()
    assert (
        ctx.processar.executar(ctx.evento(TipoEvento.PAGAMENTO_APROVADO, pid, valor=1))
        == Resultado.REJEITADO
    )
    assert ctx.metricas.suspeitos == 1
    desconhecido = EventoGateway("e", TipoEvento.PAGAMENTO_APROVADO, "tx_nao_existe", 1, 2)
    assert ctx.processar.executar(desconhecido) == Resultado.IGNORADO
    pg = ctx.repo.obter(pid)
    assert pg is not None
    assert pg.status == StatusPagamento.PENDENTE


def test_aprovacao_tardia_apos_expirar_gera_estorno(ctx: Ctx) -> None:
    pid = ctx.emitir()
    CancelarCodigo(ctx.repo, ctx.gateway).executar(pid, "EXPIRADO")
    pg = ctx.repo.obter(pid)
    assert pg is not None
    assert pg.status == StatusPagamento.EXPIRADO
    assert (
        ctx.processar.executar(ctx.evento(TipoEvento.PAGAMENTO_APROVADO, pid))
        == Resultado.PROCESSADO
    )
    pg = ctx.repo.obter(pid)
    assert pg is not None
    assert pg.status == StatusPagamento.APROVADO_TARDIO
    assert ctx.estorno.pedidos == [pid]
    assert ctx.metricas.tardios == 1


def test_token_consumido_nao_prova_pagamento_tardio(ctx: Ctx) -> None:
    pid = ctx.emitir()
    ctx.repo.registrar_token(pid, "tok")
    ctx.saga.consumido = True
    ctx.processar.executar(ctx.evento(TipoEvento.PAGAMENTO_APROVADO, pid))
    pg = ctx.repo.obter(pid)
    assert pg is not None
    assert pg.status == StatusPagamento.APROVADO
    assert ctx.estorno.pedidos == []


def test_estorno_e_conclusao(ctx: Ctx) -> None:
    pid = ctx.emitir()
    with pytest.raises(EstadoInvalido):
        Estornar(ctx.repo, ctx.gateway).executar(pid)  # ainda PENDENTE
    ctx.processar.executar(ctx.evento(TipoEvento.PAGAMENTO_APROVADO, pid))
    Estornar(ctx.repo, ctx.gateway).executar(pid)
    Estornar(ctx.repo, ctx.gateway).executar(pid)  # idempotente
    assert ctx.gateway.estornos == ["tx_" + pid[:8]]
    ctx.processar.executar(ctx.evento(TipoEvento.ESTORNO_CONCLUIDO, pid, seq=3, eid="e9"))
    pg = ctx.repo.obter(pid)
    assert pg is not None
    assert pg.status == StatusPagamento.ESTORNADO
    assert pg.estorno is not None
    assert pg.estorno["status"] == "CONCLUIDO"


def test_cancelar_codigo_so_atua_em_pendente(ctx: Ctx) -> None:
    pid = ctx.emitir()
    CancelarCodigo(ctx.repo, ctx.gateway).executar(pid, "DESISTENCIA")
    CancelarCodigo(ctx.repo, ctx.gateway).executar(pid, "DESISTENCIA")
    assert len(ctx.gateway.canceladas) == 2
    pg = ctx.repo.obter(pid)
    assert pg is not None
    assert pg.status == StatusPagamento.CANCELADO


def test_assinatura_do_webhook() -> None:
    agora = int(time.time())
    corpo = '{"a":1}'
    cab = assinatura_webhook.assinar("segredo", agora, corpo)
    assert assinatura_webhook.verificar(
        cab, corpo, ["x", "segredo"], agora
    )  # aceita atual/anterior
    assert not assinatura_webhook.verificar(cab, corpo + " ", ["segredo"], agora)
    assert not assinatura_webhook.verificar(cab, corpo, ["outro"], agora)
    assert not assinatura_webhook.verificar(cab, corpo, ["segredo"], agora + 301)  # replay
    assert not assinatura_webhook.verificar(None, corpo, ["segredo"], agora)
    assert not assinatura_webhook.verificar("lixo", corpo, ["segredo"], agora)


def test_json_serializavel() -> None:
    assert json.dumps({"resultado": Resultado.PROCESSADO.value})


def _ignorar(_: Any) -> None:  # mantem Any importado para tipagem de fixtures futuras
    return None


@pytest.mark.parametrize("tipo", [TipoEvento.PAGAMENTO_APROVADO, TipoEvento.PAGAMENTO_RECUSADO])
def test_reentrega_recupera_callback_apos_falha(
    ctx: Ctx, tipo: TipoEvento, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = ctx.emitir()
    ctx.repo.registrar_token(pid, "tok")
    metodo = "enviar_sucesso" if tipo == TipoEvento.PAGAMENTO_APROVADO else "enviar_falha"
    original = getattr(ctx.saga, metodo)

    def falha(*args: Any) -> bool:
        raise TimeoutError("timeout")

    monkeypatch.setattr(ctx.saga, metodo, falha)
    evento = ctx.evento(tipo, pid)
    with pytest.raises(TimeoutError):
        ctx.processar.executar(evento)
    monkeypatch.setattr(ctx.saga, metodo, original)
    assert ctx.processar.executar(evento) == Resultado.PROCESSADO
    assert ctx.saga.sucessos or ctx.saga.falhas
    assert ctx.estorno.pedidos == []


def test_cancelamento_compensa_aprovacao_com_callback_perdido(ctx: Ctx) -> None:
    pid = ctx.emitir()
    ctx.processar.executar(ctx.evento(TipoEvento.PAGAMENTO_APROVADO, pid))
    CancelarCodigo(ctx.repo, ctx.gateway).executar(pid, "EXPIRADO")
    CancelarCodigo(ctx.repo, ctx.gateway).executar(pid, "EXPIRADO")
    assert len(ctx.gateway.estornos) == 1
    assert ctx.gateway.canceladas == []


def test_cancelamento_retentavel_apos_falha_gateway(
    ctx: Ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = ctx.emitir()
    original = ctx.gateway.cancelar_cobranca

    def falha(tx: str) -> None:
        raise TimeoutError("timeout")

    monkeypatch.setattr(ctx.gateway, "cancelar_cobranca", falha)
    with pytest.raises(TimeoutError):
        CancelarCodigo(ctx.repo, ctx.gateway).executar(pid, "EXPIRADO")
    monkeypatch.setattr(ctx.gateway, "cancelar_cobranca", original)
    CancelarCodigo(ctx.repo, ctx.gateway).executar(pid, "EXPIRADO")
    assert len(ctx.gateway.canceladas) == 1


def test_reentrega_recupera_solicitacao_estorno_tardio(
    ctx: Ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = ctx.emitir()
    CancelarCodigo(ctx.repo, ctx.gateway).executar(pid, "EXPIRADO")
    original = ctx.estorno.solicitar_async

    def falha(pagamento_id: str) -> None:
        raise TimeoutError("timeout")

    monkeypatch.setattr(ctx.estorno, "solicitar_async", falha)
    evento = ctx.evento(TipoEvento.PAGAMENTO_APROVADO, pid)
    with pytest.raises(TimeoutError):
        ctx.processar.executar(evento)
    monkeypatch.setattr(ctx.estorno, "solicitar_async", original)
    ctx.processar.executar(evento)
    assert ctx.estorno.pedidos == [pid]
