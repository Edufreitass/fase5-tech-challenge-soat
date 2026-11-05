import json
import re
from collections.abc import Iterator
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from migration_runner.adapters.aws import CognitoFuncionarios, SsmParametros
from migration_runner.adapters.handler import carregar_diretorio
from migration_runner.adapters.vehicles import CadastroVeiculosMigracao
from migration_runner.adapters.yaml_loader import carregar
from migration_runner.application.executor import ChecksumDivergente, ExecutorMigracoes
from migration_runner.domain.models import MigracaoInvalida
from shared.crypto import gerar_par_chaves
from vehicles.adapters.dynamodb.repository import DynamoDBVeiculoRepository
from vehicles.application.registration import CadastrarVeiculo
from vehicles.domain.models import StatusVeiculo

DIRETORIO = Path(__file__).resolve().parents[3] / "data_migrations"


def migracao(nome: str, texto: str):  # type: ignore[no-untyped-def]
    return carregar(nome, texto.encode())


@pytest.fixture
def aws() -> Iterator[tuple[ExecutorMigracoes, SsmParametros, str]]:
    with mock_aws():
        cognito = boto3.client("cognito-idp")
        pool = cognito.create_user_pool(PoolName="f", UsernameAttributes=["email"])["UserPool"][
            "Id"
        ]
        cognito.create_group(UserPoolId=pool, GroupName="admin")
        ssm = SsmParametros(boto3.client("ssm"), "/revenda/dev")
        yield (
            ExecutorMigracoes(ssm, CognitoFuncionarios(cognito, pool), gerar_par_chaves),
            ssm,
            pool,
        )


def test_arquivos_reais_sao_validos_e_sem_valores_sensiveis() -> None:
    migracoes = carregar_diretorio(DIRETORIO)
    assert [m.versao for m in migracoes] == [1, 2, 3]
    for arquivo in DIRETORIO.glob("V*.yml"):
        texto = arquivo.read_text()
        assert not re.search(r"@[\w-]+\.\w+", texto.replace("${param:", "")), "e-mail literal"
        assert not re.search(r"AKIA|BEGIN .*KEY|password|senha", texto, re.IGNORECASE)


def test_aplica_tudo_e_e_idempotente(aws) -> None:  # type: ignore[no-untyped-def]
    executor, ssm, pool = aws
    migracoes = carregar_diretorio(DIRETORIO)[:2]  # V003 exige a tabela de veiculos
    primeira = executor.executar(migracoes)
    assert [a["versao"] for a in primeira] == ["V001", "V002"]
    for segredo in ("webhook-hmac-atual", "cpf-hmac", "cursor-hmac", "pii-chave-privada-v1"):
        assert ssm.existe(f"segredos/{segredo}")
    assert ssm.ler("pii/versao-atual") == "1"
    assert ssm.ler("pii/chave-publica-v1")
    historico = json.loads(ssm.ler("migracoes/V002") or "")
    assert set(historico) == {"checksum", "aplicadaEm", "duracaoMs"}
    users = boto3.client("cognito-idp").list_users(UserPoolId=pool)["Users"]
    assert users == []  # nenhuma migracao cria usuarios
    assert executor.executar(migracoes) == []  # segundo deploy nao reaplica nada


def test_segredo_nao_e_regerado(aws) -> None:  # type: ignore[no-untyped-def]
    executor, ssm, _ = aws
    segredo = migracao(
        "V001__s.yml",
        "versao: 1\ndescricao: x\noperacoes:\n"
        "  - {operacao: ssm.gerar_segredo, nome: a, bytes: 8}\n",
    )
    executor.executar([segredo])
    original = ssm._ssm.get_parameter(Name="/revenda/dev/segredos/a", WithDecryption=True)
    ssm._ssm.delete_parameter(Name="/revenda/dev/migracoes/V001")  # forca reexecucao
    executor.executar([segredo])
    assert (
        ssm._ssm.get_parameter(Name="/revenda/dev/segredos/a", WithDecryption=True)["Parameter"][
            "Value"
        ]
        == original["Parameter"]["Value"]
    )


def test_checksum_divergente_falha(aws) -> None:  # type: ignore[no-untyped-def]
    executor, _, _ = aws
    base = (
        "versao: 1\ndescricao: {}\noperacoes:\n  - {{operacao: ssm.gerar"
        "_segredo, nome: a, bytes: 8}}\n"
    )
    executor.executar([migracao("V001__a.yml", base.format("um"))])
    with pytest.raises(ChecksumDivergente):
        executor.executar([migracao("V001__a.yml", base.format("dois"))])


def test_param_ausente_falha(aws) -> None:  # type: ignore[no-untyped-def]
    executor, _, _ = aws
    m = migracao(
        "V009__x.yml",
        "versao: 9\ndescricao: x\noperacoes:\n"
        "  - {operacao: cognito.criar_funcionario, "
        "email: '${param:nao-existe}', nome: N, grupo: admin}\n",
    )
    with pytest.raises(MigracaoInvalida):
        executor.executar([m])


def test_versoes_duplicadas(aws) -> None:  # type: ignore[no-untyped-def]
    executor, _, _ = aws
    m = migracao("V001__a.yml", "versao: 1\ndescricao: x\noperacoes: []\n")
    with pytest.raises(MigracaoInvalida):
        executor.executar([m, m])


@pytest.mark.parametrize(
    ("nome", "texto"),
    [
        ("v1_ruim.yml", "versao: 1\ndescricao: x\noperacoes: []\n"),
        ("V001__a.yml", "versao: 2\ndescricao: x\noperacoes: []\n"),
        ("V001__a.yml", "versao: 1\ndescricao: x\noperacoes: []\nextra: 1\n"),
        ("V001__a.yml", "versao: 1\ndescricao: x\noperacoes:\n  - {operacao: shell.exec}\n"),
        (
            "V001__a.yml",
            "versao: 1\ndescricao: x\noperacoes:\n  - {operacao: ssm.gerar_segredo, nome: a}\n",
        ),
        (
            "V001__a.yml",
            "versao: 1\ndescricao: x\noperacoes:\n"
            "  - {operacao: cognito.criar_funcionario, email: a@b.com, nome: N, grupo: admin}\n",
        ),
    ],
)
def test_migracoes_invalidas(nome: str, texto: str) -> None:
    with pytest.raises(MigracaoInvalida):
        carregar(nome, texto.encode())


def test_v003_cadastra_20_veiculos_de_forma_idempotente(monkeypatch: pytest.MonkeyPatch) -> None:
    with mock_aws():
        ddb = boto3.client("dynamodb")
        ddb.create_table(
            TableName="t",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": a, "AttributeType": "S"}
                for a in ("pk", "sk", "gsi1pk", "gsi1sk")
            ],
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "gsi_status_preco",
                    "KeySchema": [
                        {"AttributeName": "gsi1pk", "KeyType": "HASH"},
                        {"AttributeName": "gsi1sk", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        )
        repo = DynamoDBVeiculoRepository(ddb, "t")
        cadastro = CadastroVeiculosMigracao(CadastrarVeiculo(repo), pausa=0)
        v003 = carregar_diretorio(DIRETORIO)[2]
        assert v003.versao == 3
        operacao = v003.operacoes[0]
        for item in operacao.parametros["itens"]:
            cadastro.cadastrar(item)
        for item in operacao.parametros["itens"]:
            cadastro.cadastrar(item)  # reexecucao: chassi existente = sucesso
        itens, _ = repo.listar_por_status(
            StatusVeiculo.DISPONIVEL,
            limite=50,
            cursor=None,
        )
        assert len(itens) == 20
        precos = [i.preco_centavos for i in itens]
        assert precos == sorted(precos)


@pytest.mark.parametrize(
    "operacoes",
    ["{}", "null", "texto", "[null]", "[42]", "[{operacao: []}]", "["],
)
def test_entrada_malformada_retorna_erro_de_migracao(operacoes: str) -> None:
    with pytest.raises(MigracaoInvalida):
        carregar("V001__a.yml", f"versao: 1\ndescricao: x\noperacoes: {operacoes}\n".encode())
