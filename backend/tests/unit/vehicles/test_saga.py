"""Passos da saga sobre o veiculo: condicionais e
idempotentes."""

from collections.abc import Iterator

import boto3
import pytest
from moto import mock_aws

from shared.errors import EstadoInvalido
from tests.tables import criar_tabelas
from tests.unit.sales.test_reservation import renavam
from vehicles.adapters.dynamodb.repository import DynamoDBVeiculoRepository
from vehicles.application.registration import CadastrarVeiculo
from vehicles.application.saga import PassosVeiculo
from vehicles.domain.models import NovoVeiculo, StatusVeiculo


@pytest.fixture
def amb() -> Iterator[tuple[DynamoDBVeiculoRepository, str]]:
    with mock_aws():
        ddb = boto3.client("dynamodb")
        criar_tabelas(ddb)
        repo = DynamoDBVeiculoRepository(ddb, "t-veiculos")
        v = CadastrarVeiculo(repo).executar(
            NovoVeiculo(
                "Fiat", "Uno", 2020, 2020, "Azul", "1000.00", 1, renavam(1), "9BXDMK00000000001"
            ),
            "t",
        )
        ddb.update_item(
            TableName="t-veiculos",
            Key={"pk": {"S": f"VEICULO#{v.id}"}, "sk": {"S": "META"}},
            UpdateExpression="SET #s = :r, vendaAtualId = :v, gsi1pk = :g",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":r": {"S": "RESERVADO"},
                ":v": {"S": "venda-1"},
                ":g": {"S": "STATUS#RESERVADO"},
            },
        )
        yield repo, v.id


def status(repo: DynamoDBVeiculoRepository, vid: str) -> StatusVeiculo:
    v = repo.obter(vid)
    assert v is not None
    return v.status


def test_ciclo_feliz_e_idempotencia(amb: tuple[DynamoDBVeiculoRepository, str]) -> None:
    repo, vid = amb
    passos = PassosVeiculo(repo)
    passos.executar("AGUARDANDO_RETIRADA", vid, "venda-1")
    passos.executar("AGUARDANDO_RETIRADA", vid, "venda-1")  # repeticao
    assert status(repo, vid) == StatusVeiculo.AGUARDANDO_RETIRADA
    passos.executar("BAIXAR_VEICULO", vid, "venda-1")
    passos.executar("BAIXAR_VEICULO", vid, "venda-1")
    assert status(repo, vid) == StatusVeiculo.VENDIDO
    vendidos, _ = repo.listar_por_status(StatusVeiculo.VENDIDO, limite=5, cursor=None)
    assert [v.id for v in vendidos] == [vid]  # listagem de vendidos


def test_liberar_volta_a_disponivel_e_e_idempotente(
    amb: tuple[DynamoDBVeiculoRepository, str],
) -> None:
    repo, vid = amb
    passos = PassosVeiculo(repo)
    passos.executar("LIBERAR_VEICULO", vid, "venda-1")
    passos.executar("LIBERAR_VEICULO", vid, "venda-1")
    v = repo.obter(vid)
    assert v is not None
    assert (v.status, v.venda_atual_id) == (StatusVeiculo.DISPONIVEL, None)
    assert [
        x.id for x in repo.listar_por_status(StatusVeiculo.DISPONIVEL, limite=5, cursor=None)[0]
    ] == [vid]


def test_venda_diferente_nao_mexe_no_veiculo(amb: tuple[DynamoDBVeiculoRepository, str]) -> None:
    repo, vid = amb
    PassosVeiculo(repo).executar(
        "LIBERAR_VEICULO", vid, "outra-venda"
    )  # compensacao de venda antiga: sucesso sem efeito
    assert status(repo, vid) == StatusVeiculo.RESERVADO
    with pytest.raises(EstadoInvalido):
        PassosVeiculo(repo).executar("AGUARDANDO_RETIRADA", vid, "outra-venda")
    with pytest.raises(EstadoInvalido):
        PassosVeiculo(repo).executar(
            "BAIXAR_VEICULO", vid, "venda-1"
        )  # ainda nao aguardava retirada
    with pytest.raises(ValueError, match="desconhecida"):
        PassosVeiculo(repo).executar("X", vid, "venda-1")
