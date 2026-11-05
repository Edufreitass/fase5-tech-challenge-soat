"""LGPD: exportacao (1 por 24 h), exclusao/anonimizacao, retencao
por
inatividade e recifragem.
"""

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from customers.adapters.api import handler as modulo
from customers.adapters.cognito.removal import CognitoRemocao
from customers.adapters.crypto.fields import CifradorSealedBox, DecifradorSealedBox, HasherHmac
from customers.adapters.dynamodb.repository import DynamoDBClienteRepository
from customers.adapters.dynamodb.sales import VendasEmAndamentoDynamo
from customers.application.data_protection import AnonimizarCliente, ExecutarRetencao
from customers.application.rotation import RecifrarCampos
from shared import crypto as cripto
from tests.tables import criar_tabelas
from tests.unit.customers.test_api import CORPO, Ambiente, amb, chamar  # noqa: F401


class InternoFake:
    def __init__(self, amb: Ambiente) -> None:
        self.decifrador = DecifradorSealedBox(lambda _v: amb.privada)
        self.repo = DynamoDBClienteRepository(amb.ddb, "t-clientes")

    def exportar_dados(self, cliente_id: str) -> dict[str, Any]:
        from customers.application.query import ExportarDadosTitular

        return ExportarDadosTitular(self.repo, self.decifrador).executar(cliente_id)


@pytest.fixture
def lgpd(amb: Ambiente, monkeypatch: pytest.MonkeyPatch) -> Ambiente:
    criar_tabelas(amb.ddb)  # t-vendas & cia
    vendas = VendasEmAndamentoDynamo(amb.ddb, "t-vendas")
    monkeypatch.setattr(modulo, "_vendas_em_andamento", lambda: vendas)
    monkeypatch.setattr(modulo, "_vendas_do_cliente", lambda: vendas)
    monkeypatch.setattr(modulo, "_anonimizador", lambda: anonimizador(amb))
    monkeypatch.setattr(modulo, "InvocadorClientesInterno", lambda *_: InternoFake(amb))
    monkeypatch.setattr(
        modulo, "PublicadorSns", lambda *_: type("P", (), {"publicar": lambda *_a, **_k: None})()
    )
    monkeypatch.setenv("CLIENTES_INTERNO_FUNCAO", "interno")
    return amb


def anonimizador(amb: Ambiente) -> AnonimizarCliente:
    return AnonimizarCliente(
        DynamoDBClienteRepository(amb.ddb, "t-clientes"),
        VendasEmAndamentoDynamo(amb.ddb, "t-vendas"),
        HasherHmac("segredo-hmac"),
        CognitoRemocao(amb.cognito, amb.pool),
    )


def cadastrar(
    amb: Ambiente, email: str = "maria@example.com", cpf: str = "529.982.247-25"
) -> dict[str, str]:
    claims = amb.usuario(email)
    assert chamar("POST", "/clientes", claims, {**CORPO, "cpf": cpf})[0] == 201
    return claims


def venda(
    amb: Ambiente, cliente_id: str, venda_id: str, status: str, *, lock: bool = False
) -> None:
    item: dict[str, Any] = {
        "pk": {"S": f"VENDA#{venda_id}"},
        "sk": {"S": "META"},
        "id": {"S": venda_id},
        "status": {"S": status},
        "gsi1pk": {"S": f"CLIENTE#{cliente_id}"},
        "gsi1sk": {"S": f"2026-10-01T00:00:00.000Z#{venda_id}"},
        "precoNegociadoCentavos": {"N": "100"},
        "criadoEm": {"S": "2026-10-01T00:00:00.000Z"},
        "atualizadoEm": {"S": "2026-10-02T00:00:00.000Z"},
        "veiculoSnapshot": {"M": {"marca": {"S": "Fiat"}}},
        "gsi2pk": {"S": f"STATUS#{status}"},
        "gsi2sk": {"S": f"2026-10-01T00:00:00.000Z#{venda_id}"},
    }
    amb.ddb.put_item(TableName="t-vendas", Item=item)
    if lock:
        amb.ddb.put_item(
            TableName="t-vendas",
            Item={
                "pk": {"S": f"CLIENTE#{cliente_id}"},
                "sk": {"S": "RESERVA_ATIVA"},
                "vendaId": {"S": venda_id},
            },
        )


def test_exportacao_traz_dados_decifrados_e_limita_a_uma_por_dia(lgpd: Ambiente) -> None:
    claims = cadastrar(lgpd)
    venda(lgpd, claims["sub"], "v1", "CONCLUIDO")
    status, corpo, headers = chamar("GET", "/clientes/meu-perfil/exportacao", claims)
    assert status == 200
    assert headers["Cache-Control"] == "no-store"
    assert corpo["titular"]["cpf"] == "52998224725"  # claro, so para o proprio titular
    assert corpo["titular"]["rg"]["numero"] == "12.345.678-9"
    assert corpo["titular"]["email"] == "maria@example.com"
    assert len(corpo["consentimentos"]) == 1
    assert [v["id"] for v in corpo["vendas"]] == ["v1"]
    status, erro, _ = chamar("GET", "/clientes/meu-perfil/exportacao", claims)
    assert (status, erro["type"]) == (429, "urn:revenda:problema:limite-excedido")
    itens = [
        i
        for i in lgpd.ddb.scan(TableName="t-clientes")["Items"]
        if i["sk"]["S"].startswith("LGPD#")
    ]
    assert sorted((i["operacao"]["S"], i["status"]["S"]) for i in itens) == [
        ("EXPORTACAO", "CONCLUIDA"),
        ("EXPORTACAO", "REJEITADA"),
    ]


def test_exportacao_sem_perfil_403(lgpd: Ambiente) -> None:
    assert (
        chamar("GET", "/clientes/meu-perfil/exportacao", lgpd.usuario("a@example.com"))[0] == 403
    )


def test_exclusao_anonimiza_libera_cpf_e_email_e_remove_o_login(lgpd: Ambiente) -> None:
    claims = cadastrar(lgpd)
    assert chamar("DELETE", "/clientes/meu-perfil", claims)[0] == 204
    perfil = lgpd.ddb.get_item(
        TableName="t-clientes",
        Key={"pk": {"S": f"CLIENTE#{claims['sub']}"}, "sk": {"S": "PERFIL"}},
    )["Item"]
    assert perfil["status"]["S"] == "ANONIMIZADO"
    assert set(perfil) <= {
        "pk",
        "sk",
        "tipo",
        "id",
        "nomeCompleto",
        "status",
        "criadoEm",
        "atualizadoEm",
        "ultimaAtividadeEm",
        "versao",
    }
    assert not [
        i
        for i in lgpd.ddb.scan(TableName="t-clientes")["Items"]
        if i["pk"]["S"].startswith(("CPF#", "EMAIL#"))
    ]
    assert lgpd.cognito.list_users(UserPoolId=lgpd.pool)["Users"] == []
    # o mesmo CPF e e-mail podem se cadastrar de novo; o perfil
    # anonimizado nao e mais acessivel
    assert chamar("GET", "/clientes/meu-perfil", claims)[0] == 403
    outro = lgpd.usuario("maria@example.com")
    assert chamar("POST", "/clientes", outro, CORPO)[0] == 201


def test_exclusao_repetida_e_idempotente(lgpd: Ambiente) -> None:
    claims = cadastrar(lgpd)
    assert chamar("DELETE", "/clientes/meu-perfil", claims)[0] == 204
    assert chamar("DELETE", "/clientes/meu-perfil", claims)[0] == 204


def test_exclusao_com_compra_em_andamento_409_e_registra_rejeicao(lgpd: Ambiente) -> None:
    claims = cadastrar(lgpd)
    venda(lgpd, claims["sub"], "v1", "AGUARDANDO_PAGAMENTO", lock=True)
    status, erro, _ = chamar("DELETE", "/clientes/meu-perfil", claims)
    assert (status, erro["type"]) == (409, "urn:revenda:problema:reserva-ativa-existente")
    rejeicoes = [
        i
        for i in lgpd.ddb.scan(TableName="t-clientes")["Items"]
        if i["sk"]["S"].startswith("LGPD#")
    ]
    assert rejeicoes[0]["motivoRejeicao"]["S"] == "VENDA_EM_ANDAMENTO"
    perfil = chamar("GET", "/clientes/meu-perfil", claims)
    assert perfil[0] == 200  # nada foi apagado


def test_exclusao_de_quem_comprou_mantem_retencao_legal_por_5_anos(lgpd: Ambiente) -> None:
    claims = cadastrar(lgpd)
    venda(lgpd, claims["sub"], "v1", "CONCLUIDO")
    assert chamar("DELETE", "/clientes/meu-perfil", claims)[0] == 204
    ret = lgpd.ddb.get_item(
        TableName="t-clientes",
        Key={"pk": {"S": f"CLIENTE#{claims['sub']}"}, "sk": {"S": "RETENCAO_LEGAL"}},
    )["Item"]
    assert ret["vendas"]["L"] == [{"S": "v1"}]
    assert "52998224725" not in json.dumps(ret)  # CPF so cifrado
    # A venda da fixture foi concluida em 02/10/2026. O TTL parte dessa
    # conclusao, e nao da data de exclusao nem do relogio da execucao.
    assert int(ret["expiraEm"]["N"]) == int(datetime(2031, 10, 2, tzinfo=UTC).timestamp())
    decifrador = DecifradorSealedBox(lambda _v: lgpd.privada)
    assert (
        decifrador.decifrar(ret["cpfCifrado"]["S"], cliente_id=claims["sub"], campo="cpf")
        == "52998224725"
    )


def test_retencao_anonimiza_so_inativos_sem_compra(lgpd: Ambiente) -> None:
    antigo, com_compra, recente = (
        cadastrar(lgpd, "a@example.com", "529.982.247-25"),
        cadastrar(lgpd, "b@example.com", "111.444.777-35"),
        cadastrar(lgpd, "c@example.com", "168.995.350-09"),
    )
    for claims in (antigo, com_compra):
        lgpd.ddb.update_item(
            TableName="t-clientes",
            Key={"pk": {"S": f"CLIENTE#{claims['sub']}"}, "sk": {"S": "PERFIL"}},
            UpdateExpression="SET ultimaAtividadeEm = :u",
            ExpressionAttributeValues={":u": {"S": "2020-01-01T00:00:00.000Z"}},
        )
    venda(lgpd, com_compra["sub"], "v9", "CANCELADO")
    repo, vendas = (
        DynamoDBClienteRepository(lgpd.ddb, "t-clientes"),
        VendasEmAndamentoDynamo(lgpd.ddb, "t-vendas"),
    )
    resumo = ExecutarRetencao(repo, vendas, anonimizador(lgpd), dias_inatividade=730).executar()
    assert resumo == {"anonimizados": 1, "comCompra": 1}
    assert repo.status_do_perfil(antigo["sub"]) == "ANONIMIZADO"
    assert repo.status_do_perfil(com_compra["sub"]) == "ATIVO"
    assert repo.status_do_perfil(recente["sub"]) == "ATIVO"
    assert ExecutarRetencao(repo, vendas, anonimizador(lgpd)).executar() == {
        "anonimizados": 0,
        "comCompra": 1,
    }  # idempotente


def test_recifragem_para_nova_chave_preserva_os_dados(lgpd: Ambiente) -> None:
    claims = cadastrar(lgpd)
    venda(lgpd, claims["sub"], "v1", "CONCLUIDO")
    chamar(
        "PATCH", "/clientes/meu-perfil", claims, None
    )  # sem If-Match: apenas ruido; o 428 nao altera nada
    assert (
        chamar(
            "DELETE", "/clientes/meu-perfil", cadastrar(lgpd, "x@example.com", "111.444.777-35")
        )[0]
        == 204
    )
    nova_privada, nova_publica = cripto.gerar_par_chaves()
    chaves = {1: lgpd.privada, 2: nova_privada}
    repo = DynamoDBClienteRepository(lgpd.ddb, "t-clientes")
    resumo = RecifrarCampos(
        repo, DecifradorSealedBox(lambda v: chaves[v]), CifradorSealedBox(nova_publica, 2)
    ).executar()
    assert resumo["falhas"] == 0
    assert resumo["recifrados"] >= 1
    perfil = repo.obter(claims["sub"])
    assert perfil is not None
    assert perfil.cpf_cifrado.startswith("k2:")
    assert perfil.rg is not None
    assert perfil.rg.numero_cifrado.startswith("k2:")
    assert (
        DecifradorSealedBox(lambda v: chaves[v]).decifrar(
            perfil.cpf_cifrado, cliente_id=claims["sub"], campo="cpf"
        )
        == "52998224725"
    )
    assert (
        RecifrarCampos(
            repo, DecifradorSealedBox(lambda v: chaves[v]), CifradorSealedBox(nova_publica, 2)
        ).executar()["recifrados"]
        == 0
    )  # idempotente
