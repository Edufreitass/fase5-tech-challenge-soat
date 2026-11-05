"""Vendas: listagens (staff e historico do cliente) e documentacao
com
justificativa/auditoria.
"""

import json
from typing import Any, ClassVar

import pytest

from sales.adapters.api import handler as modulo
from sales.application.saga import PassosVenda
from tests.unit.sales.test_api import amb, chamar  # noqa: F401
from tests.unit.sales.test_reservation import ClientesFake, Ctx
from tests.unit.sales.test_saga import PagamentosFake, SagaFake


class ClientesCompleto(ClientesFake):
    def obter_dados_documentacao(self, cliente_id: str) -> dict[str, Any]:
        return {
            "nomeCompleto": "Maria",
            "cpf": "52998224725",
            "rg": {"numero": "12.345.678-9", "orgaoEmissor": "SSP", "uf": "SP"},
            "dataNascimento": "1990-05-12",
            "endereco": {"cep": "01310100"},
        }


class AuditoriaFake:
    eventos: ClassVar[list[tuple[str, dict[str, Any]]]] = []

    def __init__(self, *_: Any) -> None:
        pass

    def publicar(self, tipo: str, dados: dict[str, Any]) -> None:
        AuditoriaFake.eventos.append((tipo, dados))


@pytest.fixture(autouse=True)
def fakes(amb: tuple[Ctx, SagaFake], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(modulo, "_clientes", ClientesCompleto)
    monkeypatch.setattr(modulo, "PublicadorSns", AuditoriaFake)
    AuditoriaFake.eventos = []


def chamar_h(
    metodo: str,
    caminho: str,
    claims: dict[str, str],
    query: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    evento = {
        "httpMethod": metodo,
        "path": caminho,
        "resource": caminho,
        "headers": headers or {},
        "multiValueHeaders": {},
        "queryStringParameters": query,
        "multiValueQueryStringParameters": {k: [v] for k, v in (query or {}).items()} or None,
        "body": None,
        "isBase64Encoded": False,
        "requestContext": {"authorizer": {"claims": claims}, "requestId": "r", "stage": "v1"},
    }
    r = modulo.handler(evento, None)
    return r["statusCode"], json.loads(r["body"] or "{}")


def test_listagem_por_status_mais_recentes_primeiro_e_paginada(
    amb: tuple[Ctx, SagaFake], claims_vendedor: dict[str, str], claims_cliente: dict[str, str]
) -> None:
    ctx, _ = amb
    ids = []
    for i in range(1, 4):
        venda = ctx.compra().executar(f"cli-{i}", ctx.veiculo(i, f"{i}0000.00"), "c")
        ids.append(venda.id)
    status, corpo = chamar_h(
        "GET", "/vendas", claims_vendedor, {"status": "RESERVADO", "limit": "2"}
    )
    assert status == 200
    assert [v["id"] for v in corpo["itens"]] == [ids[2], ids[1]]  # mais recente primeiro
    assert corpo["itens"][0]["clienteId"] == "cli-3"
    status, proxima = chamar_h(
        "GET",
        "/vendas",
        claims_vendedor,
        {"status": "RESERVADO", "limit": "2", "nextToken": corpo["nextToken"]},
    )
    assert [v["id"] for v in proxima["itens"]] == [ids[0]]
    assert proxima["nextToken"] is None
    assert chamar_h("GET", "/vendas", claims_vendedor, {"status": "CANCELADO"})[1]["itens"] == []
    assert chamar_h("GET", "/vendas", claims_vendedor, {})[0] == 422  # status obrigatorio
    assert chamar_h("GET", "/vendas", claims_cliente, {"status": "RESERVADO"})[0] == 403


def test_historico_so_traz_as_compras_do_proprio_cliente(
    amb: tuple[Ctx, SagaFake], claims_cliente: dict[str, str]
) -> None:
    ctx, saga = amb
    meu = {**claims_cliente, "sub": "cli-1"}
    primeira = ctx.compra().executar("cli-1", ctx.veiculo(1), "c")
    ctx.compra().executar("cli-2", ctx.veiculo(2), "c")  # de outro cliente
    PassosVenda(ctx.vendas, saga, PagamentosFake()).atualizar_venda(
        primeira.id,
        "RESERVADO",
        "CANCELADO",
        motivo="DESISTENCIA",
        ator="SISTEMA",
        definir={},
        prazo_retirada_segundos=None,
    )
    ctx.vendas.liberar_lock("cli-1", primeira.id)
    segunda = ctx.compra().executar("cli-1", ctx.veiculo(3), "c")
    status, corpo = chamar_h("GET", "/clientes/meu-perfil/vendas", meu)
    assert status == 200
    assert [v["id"] for v in corpo["itens"]] == [segunda.id, primeira.id]
    assert corpo["itens"][1]["motivoCancelamento"] == "DESISTENCIA"
    assert all("clienteId" not in v for v in corpo["itens"])


def _paga(ctx: Ctx, saga: SagaFake) -> str:
    venda = ctx.compra().executar("cli-1", ctx.veiculo(1), "c")
    p = PassosVenda(ctx.vendas, saga, PagamentosFake())
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
    return venda.id


def test_documentacao_exige_justificativa_pago_e_audita(
    amb: tuple[Ctx, SagaFake], claims_vendedor: dict[str, str], claims_cliente: dict[str, str]
) -> None:
    ctx, saga = amb
    venda = ctx.compra().executar("cli-1", ctx.veiculo(1), "c")
    caminho = f"/vendas/{venda.id}/documentacao"
    just = {"X-Justificativa": "Emissao da ATPV-e da venda"}
    assert chamar_h("GET", caminho, claims_cliente, headers=just)[0] == 403
    assert chamar_h("GET", caminho, claims_vendedor)[0] == 422  # sem justificativa
    assert (
        chamar_h("GET", caminho, claims_vendedor, headers={"X-Justificativa": "curta"})[0] == 422
    )
    assert (
        chamar_h("GET", caminho, claims_vendedor, headers={"X-Justificativa": "x" * 201})[0] == 422
    )
    assert (
        chamar_h("GET", caminho, claims_vendedor, headers=just)[0] == 422
    )  # ainda RESERVADA, nao PAGA
    assert AuditoriaFake.eventos == []  # nada auditado quando nada foi exposto


def test_documentacao_da_venda_paga(
    amb: tuple[Ctx, SagaFake], claims_vendedor: dict[str, str], claims_admin: dict[str, str]
) -> None:
    ctx, saga = amb
    venda_id = _paga(ctx, saga)
    status, corpo = chamar_h(
        "GET",
        f"/vendas/{venda_id}/documentacao",
        claims_admin,
        headers={"X-Justificativa": "Emissao da ATPV-e da venda"},
    )
    assert status == 200
    assert corpo["comprador"]["cpf"] == "52998224725"  # claro, so neste endpoint interno
    assert corpo["veiculo"]["renavam"] and corpo["veiculo"]["chassi"]
    tipo, dados = AuditoriaFake.eventos[0]
    assert tipo == "DadosPessoaisAcessados"
    assert (dados["vendaId"], dados["atorId"], dados["papel"]) == (
        venda_id,
        claims_admin["sub"],
        "admin",
    )
    assert "52998224725" not in json.dumps(dados)  # o evento nao carrega o dado pessoal
    assert (
        chamar_h(
            "GET",
            "/vendas/" + "x" * 40 + "/documentacao",
            claims_vendedor,
            headers={"X-Justificativa": "Emissao da ATPV-e da venda"},
        )[0]
        == 404
    )
