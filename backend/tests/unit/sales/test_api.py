"""Handlers HTTP de vendas (POST/GET/desistencia/retirada) e do outbox,
com
DynamoDB simulado.
"""

import json
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from aws_lambda_powertools.utilities import parameters
from boto3.dynamodb.types import TypeSerializer
from moto import mock_aws

from payments.adapters.dynamodb.repository import DynamoDBPagamentoRepository
from payments.domain.models import Pagamento, StatusPagamento
from sales.adapters.api import handler as modulo
from sales.adapters.outbox import handler as outbox
from sales.application.saga import IniciarSaga, PassosVenda
from sales.domain.models import Ator, StatusVenda
from shared import parameters as parametros
from tests.unit.sales.test_reservation import ClientesFake, Ctx
from tests.unit.sales.test_saga import PagamentosFake, PrazosFake, SagaFake, agora


@pytest.fixture
def amb(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Ctx, SagaFake]]:
    with mock_aws():
        ctx = Ctx()
        saga = SagaFake()
        boto3.client("ssm").put_parameter(
            Name="/revenda/dev/params/prazo-pagamento-segundos", Value="172800", Type="String"
        )

        parameters.base.DEFAULT_PROVIDERS.clear()  # type: ignore[attr-defined]
        monkeypatch.setattr(modulo, "_vendas", lambda: ctx.vendas)
        monkeypatch.setattr(modulo, "_veiculos", lambda: ctx.veiculos)
        monkeypatch.setattr(modulo, "_clientes", ClientesFake)
        monkeypatch.setattr(modulo, "_saga", lambda: saga)
        monkeypatch.setattr(
            modulo,
            "_leitor",
            lambda: modulo.LeitorPagamentoDynamo(
                DynamoDBPagamentoRepository(ctx.ddb, "t-pagamentos")
            ),
        )
        boto3.client("ssm").put_parameter(
            Name="/revenda/dev/segredos/cursor-hmac", Value="s3gredo", Type="String"
        )
        parametros.segredo_cursor.cache_clear()
        yield ctx, saga


def chamar(
    metodo: str, caminho: str, claims: dict[str, str] | None, corpo: Any = None
) -> tuple[int, Any]:
    evento = {
        "httpMethod": metodo,
        "path": caminho,
        "resource": caminho,
        "headers": {},
        "multiValueHeaders": {},
        "queryStringParameters": None,
        "body": json.dumps(corpo) if corpo is not None else None,
        "isBase64Encoded": False,
        "requestContext": {
            "authorizer": {"claims": claims} if claims else None,
            "requestId": "r",
            "stage": "v1",
        },
    }
    r = modulo.handler(evento, None)
    return r["statusCode"], json.loads(r["body"] or "{}")


def test_autorizacao_basica(
    amb: tuple[Ctx, SagaFake], claims_vendedor: dict[str, str], claims_cliente: dict[str, str]
) -> None:
    assert chamar("POST", "/vendas", None, {"veiculoId": "x"})[0] == 401
    assert (
        chamar("POST", "/vendas", claims_vendedor, {"veiculoId": "x"})[0] == 403
    )  # compra e do cliente
    assert (
        chamar("POST", "/vendas/abc/retirada", claims_cliente, {})[0] == 403
    )  # retirada e do vendedor
    assert chamar("POST", "/vendas", claims_cliente, {"veiculoId": "x", "extra": 1})[0] == 422


def test_compra_consulta_pelo_dono_e_idor(
    amb: tuple[Ctx, SagaFake], claims_cliente: dict[str, str], claims_vendedor: dict[str, str]
) -> None:
    ctx, _ = amb
    vid = ctx.veiculo()
    status, venda = chamar("POST", "/vendas", claims_cliente, {"veiculoId": vid})
    assert status == 201
    assert venda["status"] == "RESERVADO"
    assert venda["precoNegociado"] == "50000.00"
    assert venda["pagamento"] is None
    status, detalhe = chamar("GET", f"/vendas/{venda['id']}", claims_cliente)
    assert status == 200
    assert [h["para"] for h in detalhe["historico"]] == ["CRIADO", "RESERVADO"]
    assert (
        chamar("GET", f"/vendas/{venda['id']}", claims_vendedor)[0] == 200
    )  # funcionario ve qualquer venda
    intruso = {**claims_cliente, "sub": "outro-cliente"}
    assert chamar("GET", f"/vendas/{venda['id']}", intruso)[0] == 404  # anti-IDOR
    assert chamar("GET", "/vendas/" + "x" * 40, claims_cliente)[0] == 404
    # segundo cliente disputando o mesmo veiculo
    status, erro = chamar("POST", "/vendas", intruso, {"veiculoId": vid})
    assert status == 409
    assert erro["type"] == "urn:revenda:problema:veiculo-indisponivel"


def test_pagamento_aparece_depois_da_emissao(
    amb: tuple[Ctx, SagaFake], claims_cliente: dict[str, str]
) -> None:
    ctx, saga = amb
    _, venda = chamar("POST", "/vendas", claims_cliente, {"veiculoId": ctx.veiculo()})
    PassosVenda(ctx.vendas, saga, PagamentosFake()).atualizar_venda(
        venda["id"],
        "RESERVADO",
        "AGUARDANDO_PAGAMENTO",
        motivo=None,
        ator="SISTEMA",
        definir={"pagamentoId": "pg-1"},
        prazo_retirada_segundos=None,
    )
    DynamoDBPagamentoRepository(ctx.ddb, "t-pagamentos").criar(
        Pagamento(
            "pg-1",
            venda["id"],
            "000201PIX",
            5_000_000,
            StatusPagamento.PENDENTE,
            "2026-10-20T00:00:00.000Z",
            "tx_1",
            "t",
            "t",
        )
    )
    _, detalhe = chamar("GET", f"/vendas/{venda['id']}", claims_cliente)
    assert detalhe["status"] == "AGUARDANDO_PAGAMENTO"
    assert detalhe["pagamento"] == {
        "id": "pg-1",
        "metodo": "PIX",
        "status": "PENDENTE",
        "pixCopiaECola": "000201PIX",
        "valor": "50000.00",
        "expiraEm": "2026-10-20T00:00:00.000Z",
    }


def test_desistencia_e_retirada_pela_api(
    amb: tuple[Ctx, SagaFake], claims_cliente: dict[str, str], claims_vendedor: dict[str, str]
) -> None:
    ctx, saga = amb
    _, venda = chamar("POST", "/vendas", claims_cliente, {"veiculoId": ctx.veiculo()})
    vid = venda["id"]
    corpo = {
        "retiradaEm": "2026-10-21T14:00:00.000Z",
        "documentacao": {"protocolo": "ATPV-e 2026/1", "emitidaEm": "2026-10-21T13:40:00.000Z"},
        "conferencia": {"documentoApresentado": "CNH"},
    }
    assert (
        chamar("POST", f"/vendas/{vid}/retirada", claims_vendedor, corpo)[0] == 409
    )  # ainda nao esta PAGA
    assert (
        chamar("POST", f"/vendas/{vid}/desistencia", {**claims_cliente, "sub": "outro"})[0] == 404
    )
    # leva a venda ate PAGO aguardando retirada
    p = PassosVenda(ctx.vendas, saga, PagamentosFake())
    p.atualizar_venda(
        vid,
        "RESERVADO",
        "AGUARDANDO_PAGAMENTO",
        motivo=None,
        ator="SISTEMA",
        definir={},
        prazo_retirada_segundos=None,
    )
    p.atualizar_venda(
        vid,
        "AGUARDANDO_PAGAMENTO",
        "PAGO",
        motivo=None,
        ator="GATEWAY",
        definir={},
        prazo_retirada_segundos=600,
    )
    p.registrar_token("RETIRADA", vid, "tok-ret", None)
    assert chamar("POST", f"/vendas/{vid}/retirada", claims_vendedor, corpo)[0] == 202
    assert saga.sucessos[-1][0] == "tok-ret"
    status, erro = chamar("POST", f"/vendas/{vid}/desistencia", claims_cliente)
    assert (status, erro["type"]) == (409, "urn:revenda:problema:venda-nao-cancelavel")
    atual = ctx.vendas.obter(vid)
    assert atual is not None
    assert atual.documentacao is not None
    assert atual.documentacao["protocolo"] == "ATPV-e 2026/1"
    assert atual.documentacao["responsavelId"] == claims_vendedor["sub"]


def test_desistencia_202_quando_reservado(
    amb: tuple[Ctx, SagaFake], claims_cliente: dict[str, str]
) -> None:
    ctx, _ = amb
    _, venda = chamar("POST", "/vendas", claims_cliente, {"veiculoId": ctx.veiculo()})
    assert chamar("POST", f"/vendas/{venda['id']}/desistencia", claims_cliente)[0] == 202


def test_outbox_inicia_saga_e_reporta_falhas(
    amb: tuple[Ctx, SagaFake], monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, saga = amb
    venda = ctx.compra().executar("cli-1", ctx.veiculo(), "corr")
    ser = TypeSerializer()
    item = ctx.ddb.get_item(
        TableName="t-vendas", Key={"pk": {"S": f"VENDA#{venda.id}"}, "sk": {"S": "META"}}
    )["Item"]
    registro = {"dynamodb": {"NewImage": item, "SequenceNumber": "1"}}
    monkeypatch.setattr(outbox, "_iniciar", lambda: IniciarSaga(ctx.vendas, saga, PrazosFake()))
    assert outbox.handler({"Records": [registro]}, None) == {"batchItemFailures": []}
    assert saga.iniciadas[0][1] == venda.id
    atual = ctx.vendas.obter(venda.id)
    assert atual is not None
    assert atual.saga_execution_arn == f"arn:execution:{venda.id}"
    ruim = {"dynamodb": {"NewImage": {"lixo": ser.serialize(1)}, "SequenceNumber": "2"}}
    assert outbox.handler({"Records": [ruim]}, None) == {
        "batchItemFailures": [{"itemIdentifier": "2"}]
    }
    assert (atual.status, Ator.SISTEMA) == (StatusVenda.RESERVADO, Ator.SISTEMA)


def _usado(_: Any) -> None:
    agora()
