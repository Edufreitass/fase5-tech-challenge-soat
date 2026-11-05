"""fn-migracoes: invocada pelo Terraform (`aws_lambda_invocation`) a
cada
deploy.

Retorna apenas as versoes aplicadas e a duracao; nenhum valor
sensivel.
"""

import os
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config

from migration_runner.adapters.aws import CognitoFuncionarios, SsmParametros
from migration_runner.adapters.vehicles import CadastroVeiculosMigracao
from migration_runner.adapters.yaml_loader import carregar
from migration_runner.application.executor import ExecutorMigracoes
from migration_runner.domain.models import Migracao
from shared.crypto import gerar_par_chaves
from shared.logger import criar_logger
from vehicles.adapters.dynamodb.repository import DynamoDBVeiculoRepository
from vehicles.application.registration import CadastrarVeiculo

logger = criar_logger("migracoes")
DIRETORIO = (
    Path(os.environ.get("DADOS_DIR", str(Path(__file__).resolve().parents[2] / "dados")))
    / "migracoes"
)


def carregar_diretorio(diretorio: Path) -> list[Migracao]:
    arquivos = sorted(diretorio.glob("V*.yml"))
    return [carregar(a.name, a.read_bytes()) for a in arquivos]


def handler(_evento: dict[str, Any], _contexto: Any) -> dict[str, Any]:
    executor = ExecutorMigracoes(
        gerar_chaves=gerar_par_chaves,
        parametros=SsmParametros(boto3.client("ssm"), os.environ["SSM_PREFIXO"]),
        funcionarios=CognitoFuncionarios(
            boto3.client("cognito-idp"), os.environ["POOL_FUNCIONARIOS_ID"]
        ),
        veiculos=CadastroVeiculosMigracao(
            CadastrarVeiculo(
                DynamoDBVeiculoRepository(
                    boto3.client(
                        "dynamodb", config=Config(retries={"mode": "standard", "max_attempts": 10})
                    ),
                    os.environ["VEICULOS_TABELA"],
                )
            )
        ),
    )
    aplicadas = executor.executar(carregar_diretorio(DIRETORIO))
    logger.info("migracoes concluidas", extra={"aplicadas": [a["versao"] for a in aplicadas]})
    return {"aplicadas": aplicadas}
