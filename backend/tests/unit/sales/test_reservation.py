"""Reserva em duas fases: sucesso, concorrencia, lock
por
cliente e validacoes.
"""

import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import boto3
import pytest
from moto import mock_aws

from sales.adapters.dynamodb.repository import DynamoDBVendaRepository
from sales.application.purchase import IniciarCompra
from sales.domain.models import MotivoCancelamento, StatusVenda
from shared.errors import (
    CadastroIncompleto,
    PerfilClienteInexistente,
    RecursoNaoEncontrado,
    ReservaAtivaExistente,
    VeiculoIndisponivel,
)
from tests.tables import criar_tabelas
from vehicles.adapters.dynamodb.repository import DynamoDBVeiculoRepository
from vehicles.application.registration import CadastrarVeiculo
from vehicles.domain.models import NovoVeiculo, StatusVeiculo
from vehicles.domain.validation import digito_renavam


class ClientesFake:
    def __init__(self, resposta: dict[str, Any] | None = None) -> None:
        self.resposta = resposta or {"valido": True, "camposPendentes": []}

    def validar_comprador(self, cliente_id: str) -> dict[str, Any]:
        return self.resposta


def renavam(n: int) -> str:
    base = f"{n:010d}"
    return base + str(digito_renavam(base))


class ClienteSerializado:
    """Serializa as chamadas ao moto (que nao e thread-safe). A
    atomicidade
    testada continua sendo a das
    expressoes condicionais; a concorrencia real e validada no `dev`
    (Lambdas em paralelo).
    """

    def __init__(self, cliente: Any) -> None:
        self._cliente = cliente
        self._trava = threading.RLock()
        self.exceptions = cliente.exceptions

    def __getattr__(self, nome: str) -> Any:
        atributo = getattr(self._cliente, nome)
        if not callable(atributo):
            return atributo

        def chamar(*args: Any, **kwargs: Any) -> Any:
            with self._trava:
                return atributo(*args, **kwargs)

        return chamar


class Ctx:
    def __init__(self) -> None:
        ddb = ClienteSerializado(boto3.client("dynamodb"))
        criar_tabelas(ddb)
        self.vendas = DynamoDBVendaRepository(ddb, "t-vendas", "t-veiculos")
        self.veiculos = DynamoDBVeiculoRepository(ddb, "t-veiculos")
        self.ddb = ddb

    def veiculo(self, n: int = 1, preco: str = "50000.00") -> str:
        novo = NovoVeiculo(
            "Fiat", f"Mod {n}", 2022, 2022, "Branco", preco, 10, renavam(n), f"9BXDMK{n:011d}"
        )
        return CadastrarVeiculo(self.veiculos).executar(novo, "t").id

    def compra(self, clientes: ClientesFake | None = None) -> IniciarCompra:
        return IniciarCompra(
            self.vendas, self.veiculos, clientes or ClientesFake(), prazo_pagamento_segundos=172800
        )


@pytest.fixture
def ctx() -> Iterator[Ctx]:
    with mock_aws():
        yield Ctx()


def test_reserva_ok_atualiza_veiculo_lock_e_historico(ctx: Ctx) -> None:
    vid = ctx.veiculo()
    venda = ctx.compra().executar("cli-1", vid, "corr-1")
    assert venda.status == StatusVenda.RESERVADO
    assert venda.reserva_expira_em is not None
    assert venda.preco_negociado_centavos == 5_000_000
    veiculo = ctx.veiculos.obter(vid)
    assert veiculo is not None
    assert (veiculo.status.value, veiculo.versao, veiculo.venda_atual_id) == (
        "RESERVADO",
        2,
        venda.id,
    )
    assert [e.para.value for e in ctx.vendas.historico(venda.id)] == ["CRIADO", "RESERVADO"]
    assert (
        ctx.veiculos.listar_por_status(StatusVeiculo.DISPONIVEL, limite=10, cursor=None)[0] == []
    )


def test_segundo_cliente_recebe_409_e_venda_cancelada_por_conflito(ctx: Ctx) -> None:
    vid = ctx.veiculo()
    ctx.compra().executar("cli-1", vid, "c")
    with pytest.raises(VeiculoIndisponivel):
        ctx.compra().executar("cli-2", vid, "c")  # le o estado atual: ja RESERVADO


def test_corrida_da_fase_2_cancela_venda_com_conflito(ctx: Ctx) -> None:
    """Le DISPONIVEL, mas outro cliente reserva antes da transacao
    (janela
    de concorrencia).
    """
    vid = ctx.veiculo()
    caso = ctx.compra()
    original = ctx.veiculos.obter

    def leitura_antiga(veiculo_id: str):  # type: ignore[no-untyped-def]
        veiculo = original(veiculo_id)
        ctx.compra().executar("cli-1", vid, "c")  # o concorrente vence logo apos a leitura
        return veiculo

    caso.veiculos = type("R", (), {"obter": staticmethod(leitura_antiga)})()
    with pytest.raises(VeiculoIndisponivel) as exc:
        caso.executar("cli-2", vid, "c")
    venda_id = exc.value.extras["vendaId"]
    perdedora = ctx.vendas.obter(venda_id)
    assert perdedora is not None
    assert (perdedora.status, perdedora.motivo_cancelamento) == (
        StatusVenda.CANCELADO,
        MotivoCancelamento.CONFLITO_RESERVA,
    )


def test_concorrencia_dez_clientes_um_unico_vencedor(ctx: Ctx) -> None:
    """Exatamente 1 x sucesso e 9 x 409, sem reserva
    duplicada.
    """
    vid = ctx.veiculo()

    def tentar(i: int) -> str:
        try:
            ctx.compra().executar(f"cli-{i}", vid, "c")
        except VeiculoIndisponivel:
            return "409"
        return "201"

    with ThreadPoolExecutor(max_workers=10) as pool:
        resultados = list(pool.map(tentar, range(10)))
    assert resultados.count("201") == 1
    assert resultados.count("409") == 9
    veiculo = ctx.veiculos.obter(vid)
    assert veiculo is not None
    assert veiculo.versao == 2


def test_uma_reserva_ativa_por_cliente(ctx: Ctx) -> None:
    ctx.compra().executar("cli-1", ctx.veiculo(1), "c")
    with pytest.raises(ReservaAtivaExistente) as exc:
        ctx.compra().executar("cli-1", ctx.veiculo(2), "c")
    outra = ctx.vendas.obter(exc.value.extras["vendaId"])
    assert outra is not None
    assert outra.status == StatusVenda.CANCELADO
    veiculo2 = ctx.veiculos.listar_por_status(StatusVeiculo.DISPONIVEL, limite=5, cursor=None)[0]
    assert len(veiculo2) == 1  # o segundo veiculo continua disponivel (transacao reverteu)


def test_validacoes_antes_da_fase_1_nao_criam_venda(ctx: Ctx) -> None:
    vid = ctx.veiculo()
    with pytest.raises(PerfilClienteInexistente):
        ctx.compra(ClientesFake({"valido": False, "camposPendentes": ["cadastro"]})).executar(
            "c", vid, "x"
        )
    with pytest.raises(CadastroIncompleto) as exc:
        ctx.compra(ClientesFake({"valido": False, "camposPendentes": ["rg"]})).executar(
            "c", vid, "x"
        )
    assert exc.value.extras["camposPendentes"] == ["rg"]
    with pytest.raises(RecursoNaoEncontrado):
        ctx.compra().executar("c", "nao-existe", "x")
    assert ctx.ddb.scan(TableName="t-vendas")["Count"] == 0
