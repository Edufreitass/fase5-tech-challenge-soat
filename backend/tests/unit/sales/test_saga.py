"""Passos da saga no contexto Vendas: transicoes idempotentes, tokens,
desistencia, retirada e varredura."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from moto import mock_aws

from payments.adapters.dynamodb.repository import DynamoDBPagamentoRepository
from payments.domain.models import Pagamento, StatusPagamento
from sales.application.purchase import ConfirmarRetirada, ConsultarVenda, DesistirDaCompra
from sales.application.saga import IniciarSaga, PassosVenda, Varredura
from sales.domain.models import Ator, EventoVenda, StatusVenda, Venda
from shared.errors import (
    EstadoInvalido,
    RecursoNaoEncontrado,
    RetiradaIndisponivel,
    VendaNaoCancelavel,
)
from tests.unit.sales.test_reservation import ClientesFake, Ctx


class SagaFake:
    def __init__(self) -> None:
        self.iniciadas: list[tuple[dict[str, Any], str]] = []
        self.sucessos: list[tuple[str, dict[str, Any]]] = []
        self.falhas: list[tuple[str, str]] = []
        self.token_consumido = False

    def iniciar(self, entrada: dict[str, Any], nome: str) -> str:
        self.iniciadas.append((entrada, nome))
        return f"arn:execution:{nome}"

    def enviar_sucesso(self, token: str, saida: dict[str, Any]) -> bool:
        self.sucessos.append((token, saida))
        return not self.token_consumido

    def enviar_falha(self, token: str, erro: str, causa: str) -> bool:
        self.falhas.append((token, erro))
        return not self.token_consumido


class PrazosFake:
    def pagamento_segundos(self) -> int:
        return 172800

    def retirada_segundos(self) -> int:
        return 604800


class PagamentosFake:
    def __init__(self) -> None:
        self.tokens: dict[str, str] = {}
        self.estado: str | None = "PENDENTE"

    def registrar_token(self, pagamento_id: str, token: str) -> None:
        self.tokens[pagamento_id] = token

    def status(self, pagamento_id: str) -> str | None:
        return self.estado


@pytest.fixture
def ctx() -> Iterator[Ctx]:
    with mock_aws():
        yield Ctx()


@pytest.fixture
def venda(ctx: Ctx) -> Venda:
    return ctx.compra(ClientesFake()).executar("cli-1", ctx.veiculo(), "corr")


def passos(ctx: Ctx, saga: SagaFake, pagamentos: PagamentosFake | None = None) -> PassosVenda:
    return PassosVenda(ctx.vendas, saga, pagamentos or PagamentosFake())


def agora() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def test_transicao_idempotente_e_invalida(ctx: Ctx, venda: Venda) -> None:
    ctx.vendas.transicionar(
        venda.id,
        StatusVenda.RESERVADO,
        StatusVenda.AGUARDANDO_PAGAMENTO,
        agora=agora(),
        ator=Ator.SISTEMA,
        definir={"pagamentoId": "pg-1"},
    )
    ctx.vendas.transicionar(
        venda.id,
        StatusVenda.RESERVADO,
        StatusVenda.AGUARDANDO_PAGAMENTO,
        agora=agora(),
        ator=Ator.SISTEMA,
    )
    atual = ctx.vendas.obter(venda.id)
    assert atual is not None
    assert (atual.status, atual.pagamento_id, atual.versao) == (
        StatusVenda.AGUARDANDO_PAGAMENTO,
        "pg-1",
        3,
    )
    assert [e.para.value for e in ctx.vendas.historico(venda.id)].count(
        "AGUARDANDO_PAGAMENTO"
    ) == 1
    with pytest.raises(EstadoInvalido):
        ctx.vendas.transicionar(
            venda.id, StatusVenda.CRIADO, StatusVenda.RESERVADO, agora=agora(), ator=Ator.SISTEMA
        )


def test_registrar_token_e_catch_up_do_webhook_antecipado(ctx: Ctx, venda: Venda) -> None:
    saga, pg = SagaFake(), PagamentosFake()
    pg.estado = "APROVADO"  # webhook chegou antes do token
    passos(ctx, saga, pg).registrar_token("PAGAMENTO", venda.id, "tok-1", "pg-1")
    assert pg.tokens == {"pg-1": "tok-1"}
    assert saga.sucessos == [("tok-1", {"resultado": "APROVADO"})]
    atual = ctx.vendas.obter(venda.id)
    assert atual is not None
    assert (atual.task_token, atual.etapa_espera.value if atual.etapa_espera else None) == (
        "tok-1",
        "PAGAMENTO",
    )


def test_registrar_token_recusado_antecipado(ctx: Ctx, venda: Venda) -> None:
    saga, pg = SagaFake(), PagamentosFake()
    pg.estado = "RECUSADO"
    passos(ctx, saga, pg).registrar_token("PAGAMENTO", venda.id, "tok", "pg-1")
    assert saga.falhas == [("tok", "Pagamento.Recusado")]


def test_desistencia_antes_do_token_falha_a_proxima_espera(ctx: Ctx, venda: Venda) -> None:
    saga = SagaFake()
    DesistirDaCompra(ctx.vendas, saga).executar(venda.id, "cli-1")  # sem token: marca a flag
    atual = ctx.vendas.obter(venda.id)
    assert atual is not None
    assert atual.desistencia_solicitada is True
    passos(ctx, saga).registrar_token("PAGAMENTO", venda.id, "tok-1", "pg-1")
    assert saga.falhas == [("tok-1", "Venda.Desistencia")]


def test_desistencia_com_token_envia_falha_para_a_saga(ctx: Ctx, venda: Venda) -> None:
    saga = SagaFake()
    passos(ctx, saga).registrar_token("PAGAMENTO", venda.id, "tok-1", "pg-1")
    DesistirDaCompra(ctx.vendas, saga).executar(venda.id, "cli-1")
    assert saga.falhas == [("tok-1", "Venda.Desistencia")]


def test_desistencia_de_outro_cliente_e_404_e_estado_final_e_409(ctx: Ctx, venda: Venda) -> None:
    saga = SagaFake()
    with pytest.raises(RecursoNaoEncontrado):
        DesistirDaCompra(ctx.vendas, saga).executar(venda.id, "intruso")
    ctx.vendas.transicionar(
        venda.id,
        StatusVenda.RESERVADO,
        StatusVenda.AGUARDANDO_PAGAMENTO,
        agora=agora(),
        ator=Ator.SISTEMA,
    )
    ctx.vendas.transicionar(
        venda.id,
        StatusVenda.AGUARDANDO_PAGAMENTO,
        StatusVenda.CANCELADO,
        agora=agora(),
        ator=Ator.SISTEMA,
    )
    with pytest.raises(VendaNaoCancelavel):
        DesistirDaCompra(ctx.vendas, saga).executar(venda.id, "cli-1")


def _pago_aguardando_retirada(ctx: Ctx, venda: Venda, saga: SagaFake) -> None:
    p = passos(ctx, saga)
    p.atualizar_venda(
        venda.id,
        "RESERVADO",
        "AGUARDANDO_PAGAMENTO",
        motivo=None,
        ator="SISTEMA",
        definir={},
        prazo_retirada_segundos=None,
    )
    p.registrar_token("PAGAMENTO", venda.id, "tok-pag", "pg-1")
    p.atualizar_venda(
        venda.id,
        "AGUARDANDO_PAGAMENTO",
        "PAGO",
        motivo=None,
        ator="GATEWAY",
        definir={},
        prazo_retirada_segundos=604800,
    )
    p.registrar_token("RETIRADA", venda.id, "tok-ret", None)


def test_pago_limpa_token_antigo_e_define_prazo_de_retirada(ctx: Ctx, venda: Venda) -> None:
    saga = SagaFake()
    p = passos(ctx, saga)
    p.atualizar_venda(
        venda.id,
        "RESERVADO",
        "AGUARDANDO_PAGAMENTO",
        motivo=None,
        ator="SISTEMA",
        definir={},
        prazo_retirada_segundos=None,
    )
    p.registrar_token("PAGAMENTO", venda.id, "tok-pag", "pg-1")
    p.atualizar_venda(
        venda.id,
        "AGUARDANDO_PAGAMENTO",
        "PAGO",
        motivo=None,
        ator="GATEWAY",
        definir={},
        prazo_retirada_segundos=604800,
    )
    atual = ctx.vendas.obter(venda.id)
    assert atual is not None
    assert atual.task_token is None
    assert atual.retirada_limite_em is not None


def test_retirada_e_o_pivot_da_saga(ctx: Ctx, venda: Venda) -> None:
    saga = SagaFake()
    _pago_aguardando_retirada(ctx, venda, saga)
    ConfirmarRetirada(ctx.vendas, saga).executar(
        venda.id, "2026-10-21T14:00:00.000Z", {"protocolo": "ATPV-1"}
    )
    assert saga.sucessos == [("tok-ret", {"retiradaEm": "2026-10-21T14:00:00.000Z"})]
    with pytest.raises(VendaNaoCancelavel):  # depois do pivot a desistencia retorna 409
        DesistirDaCompra(ctx.vendas, saga).executar(venda.id, "cli-1")
    with pytest.raises(VendaNaoCancelavel):  # e nao ha segunda retirada
        ConfirmarRetirada(ctx.vendas, saga).executar(venda.id, "x", {})


def test_retirada_logo_apos_pagar_pede_nova_tentativa(ctx: Ctx, venda: Venda) -> None:
    saga = SagaFake()
    p = passos(ctx, saga)
    p.atualizar_venda(
        venda.id,
        "RESERVADO",
        "AGUARDANDO_PAGAMENTO",
        motivo=None,
        ator="SISTEMA",
        definir={},
        prazo_retirada_segundos=None,
    )
    p.atualizar_venda(
        venda.id,
        "AGUARDANDO_PAGAMENTO",
        "PAGO",
        motivo=None,
        ator="GATEWAY",
        definir={},
        prazo_retirada_segundos=600,
    )
    with pytest.raises(
        RetiradaIndisponivel
    ):  # a espera de retirada ainda nao foi registrada pela saga
        ConfirmarRetirada(ctx.vendas, saga).executar(venda.id, "x", {})
    p.registrar_token("RETIRADA", venda.id, "tok-ret", None)
    ConfirmarRetirada(ctx.vendas, saga).executar(
        venda.id, "2026-10-21T14:00:00.000Z", {"protocolo": "P"}
    )
    assert saga.sucessos[-1][0] == "tok-ret"


def test_retirada_exige_venda_paga(ctx: Ctx, venda: Venda) -> None:
    with pytest.raises(VendaNaoCancelavel):
        ConfirmarRetirada(ctx.vendas, SagaFake()).executar(venda.id, "x", {})


def test_desistencia_pos_pago_envia_falha_e_bloqueia_retirada(ctx: Ctx, venda: Venda) -> None:
    saga = SagaFake()
    _pago_aguardando_retirada(ctx, venda, saga)
    DesistirDaCompra(ctx.vendas, saga).executar(venda.id, "cli-1")
    assert saga.falhas[-1] == ("tok-ret", "Venda.Desistencia")
    with pytest.raises(VendaNaoCancelavel):
        ConfirmarRetirada(ctx.vendas, saga).executar(venda.id, agora(), {"protocolo": "P"})
    assert saga.sucessos == []


def test_desistencia_persiste_se_callback_falha_e_pode_ser_retentada(
    ctx: Ctx, venda: Venda, monkeypatch: pytest.MonkeyPatch
) -> None:
    saga = SagaFake()
    _pago_aguardando_retirada(ctx, venda, saga)
    original = saga.enviar_falha

    def indisponivel(*args: Any) -> bool:
        raise TimeoutError("servico temporariamente indisponivel")

    monkeypatch.setattr(saga, "enviar_falha", indisponivel)
    with pytest.raises(TimeoutError):
        DesistirDaCompra(ctx.vendas, saga).executar(venda.id, "cli-1")
    with pytest.raises(VendaNaoCancelavel):
        ConfirmarRetirada(ctx.vendas, saga).executar(venda.id, agora(), {})
    monkeypatch.setattr(saga, "enviar_falha", original)
    DesistirDaCompra(ctx.vendas, saga).executar(venda.id, "cli-1")
    assert saga.falhas == [("tok-ret", "Venda.Desistencia")]


def test_desistencia_com_token_consumido_bloqueia_proxima_espera(ctx: Ctx, venda: Venda) -> None:
    saga = SagaFake()
    passos(ctx, saga).registrar_token("PAGAMENTO", venda.id, "tok-pag", "pg-1")
    saga.token_consumido = True
    DesistirDaCompra(ctx.vendas, saga).executar(venda.id, "cli-1")
    saga.token_consumido = False
    passos(ctx, saga).registrar_token("RETIRADA", venda.id, "tok-ret", None)
    assert saga.falhas[-1] == ("tok-ret", "Venda.Desistencia")


def test_consulta_so_do_dono_ou_funcionario(ctx: Ctx, venda: Venda) -> None:
    class Leitor:
        def por_id(self, pagamento_id: str) -> None:
            return None

    consulta = ConsultarVenda(ctx.vendas, Leitor())
    assert consulta.executar(venda.id, solicitante_id="cli-1", funcionario=False)[0].id == venda.id
    assert consulta.executar(venda.id, solicitante_id="vend", funcionario=True)[0].id == venda.id
    with pytest.raises(RecursoNaoEncontrado):
        consulta.executar(venda.id, solicitante_id="outro", funcionario=False)


def test_varredura_inicia_sagas_orfas_e_cancela_criadas_antigas(ctx: Ctx, venda: Venda) -> None:
    saga = SagaFake()
    iniciar = IniciarSaga(ctx.vendas, saga, PrazosFake())
    futuro = datetime.now(UTC) + timedelta(minutes=20)
    r = Varredura(ctx.vendas, iniciar, relogio=lambda: futuro).executar()
    assert r == {"sagasIniciadas": 1, "criadasCanceladas": 0}
    entrada, nome = saga.iniciadas[0]
    assert nome == venda.id
    assert entrada["prazos"] == {"pagamentoSegundos": 172800, "retiradaSegundos": 604800}
    assert "cpf" not in str(entrada).lower()
    assert (
        Varredura(ctx.vendas, iniciar, relogio=lambda: futuro).executar()["sagasIniciadas"] == 0
    )  # ja tem saga
    # venda CRIADA antiga (falha entre fases 1 e 2)
    outra = Venda(
        id="v-x",
        cliente_id="c2",
        veiculo_id="vx",
        veiculo_snapshot={},
        preco_negociado_centavos=1,
        status=StatusVenda.CRIADO,
        versao=1,
        criado_em=agora(),
        atualizado_em=agora(),
        correlation_id="c",
    )
    ctx.vendas.criar(outra, EventoVenda(StatusVenda.CRIADO, Ator.CLIENTE, agora()))
    assert (
        Varredura(ctx.vendas, iniciar, relogio=lambda: futuro).executar()["criadasCanceladas"] == 1
    )
    cancelada = ctx.vendas.obter("v-x")
    assert cancelada is not None
    assert cancelada.status == StatusVenda.CANCELADO


def test_pagamento_repositorio_usado_pelo_worker(ctx: Ctx) -> None:
    repo = DynamoDBPagamentoRepository(ctx.ddb, "t-pagamentos")
    repo.criar(
        Pagamento(
            "pg-1",
            "v",
            "pix",
            100,
            StatusPagamento.PENDENTE,
            "2026-10-20T00:00:00.000Z",
            "tx_1",
            "t",
            "t",
        )
    )
    repo.registrar_token("pg-1", "tok")
    lido = repo.obter("pg-1")
    assert lido is not None
    assert lido.task_token == "tok"


@pytest.mark.parametrize("alvo", [StatusVenda.PAGO, StatusVenda.CONCLUIDO, StatusVenda.ESTORNADO])
def test_repositorio_nao_persiste_salto_de_etapas(
    ctx: Ctx, venda: Venda, alvo: StatusVenda
) -> None:
    historico = ctx.vendas.historico(venda.id)
    with pytest.raises(EstadoInvalido):
        ctx.vendas.transicionar(
            venda.id, StatusVenda.RESERVADO, alvo, agora=agora(), ator=Ator.SISTEMA
        )
    assert ctx.vendas.obter(venda.id) == venda
    assert ctx.vendas.historico(venda.id) == historico


def test_retirada_callback_transitorio_retentavel(ctx: Ctx, venda: Venda) -> None:
    class SagaIndisponivel(SagaFake):
        def enviar_sucesso(self, token: str, saida: dict[str, Any]) -> bool:
            raise TimeoutError("timeout")

    saga = SagaIndisponivel()
    _pago_aguardando_retirada(ctx, venda, saga)
    documento = {"protocolo": "ATPV-1"}
    momento = agora()
    with pytest.raises(TimeoutError):
        ConfirmarRetirada(ctx.vendas, saga).executar(venda.id, momento, documento)
    recuperada = SagaFake()
    ConfirmarRetirada(ctx.vendas, recuperada).executar(venda.id, momento, documento)
    assert recuperada.sucessos == [("tok-ret", {"retiradaEm": momento})]
    assert ctx.vendas.encerrar_retirada(venda.id) is True


def test_timeout_retirada_vence_e_impede_retirada_tardia(ctx: Ctx, venda: Venda) -> None:
    saga = SagaFake()
    _pago_aguardando_retirada(ctx, venda, saga)
    assert ctx.vendas.encerrar_retirada(venda.id) is False
    assert ctx.vendas.encerrar_retirada(venda.id) is False
    with pytest.raises(VendaNaoCancelavel):
        ConfirmarRetirada(ctx.vendas, saga).executar(venda.id, agora(), {})
    assert saga.sucessos == []


def test_retirada_vence_timeout_mesmo_com_token_expirado(ctx: Ctx, venda: Venda) -> None:
    saga = SagaFake()
    _pago_aguardando_retirada(ctx, venda, saga)
    saga.token_consumido = True
    ConfirmarRetirada(ctx.vendas, saga).executar(venda.id, agora(), {})
    assert ctx.vendas.encerrar_retirada(venda.id) is True
    with pytest.raises(VendaNaoCancelavel):
        DesistirDaCompra(ctx.vendas, saga).executar(venda.id, "cli-1")
