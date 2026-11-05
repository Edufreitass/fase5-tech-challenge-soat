"""fn-lgpd-worker: retencao diaria (Scheduler) e recifragem apos a
rotacao
da chave PII.

Junto com fn-clientes-interno, e a unica funcao autorizada a ler
`segredos/pii-chave-privada-*`.
"""

import os
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config

from customers.adapters.cognito.removal import CognitoRemocao
from customers.adapters.crypto.fields import CifradorSealedBox, DecifradorSealedBox, HasherHmac
from customers.adapters.dynamodb.repository import DynamoDBClienteRepository
from customers.adapters.dynamodb.sales import VendasEmAndamentoDynamo
from customers.application.data_protection import AnonimizarCliente, ExecutarRetencao
from customers.application.rotation import RecifrarCampos
from shared import parameters as parametros
from shared.logger import criar_logger

logger = criar_logger("lgpd-worker")


@lru_cache(maxsize=1)
def _ddb() -> Any:
    return boto3.client("dynamodb", config=Config(retries={"mode": "standard", "max_attempts": 8}))


@lru_cache(maxsize=1)
def _repositorio() -> DynamoDBClienteRepository:
    return DynamoDBClienteRepository(_ddb(), os.environ["CLIENTES_TABELA"])


def _chave_privada(versao: int) -> str:
    return parametros.obter(f"segredos/pii-chave-privada-v{versao}", segredo=True)


def _retencao() -> ExecutarRetencao:
    vendas = VendasEmAndamentoDynamo(_ddb(), os.environ["VENDAS_TABELA"])
    anonimizar = AnonimizarCliente(
        _repositorio(),
        vendas,
        HasherHmac(parametros.obter("segredos/cpf-hmac", segredo=True)),
        CognitoRemocao(boto3.client("cognito-idp"), os.environ["POOL_CLIENTES_ID"]),
    )
    dias = int(parametros.obter("params/retencao-inativos-dias"))
    return ExecutarRetencao(_repositorio(), vendas, anonimizar, dias_inatividade=dias)


def handler(evento: dict[str, Any], _contexto: Any) -> dict[str, Any]:
    acao = evento.get("acao")
    logger.info("acao", extra={"acao": acao})
    if acao == "RETENCAO":
        return _retencao().executar()
    if acao == "RECIFRAR":
        versao = int(evento["versaoNova"])
        publica = parametros.obter(f"pii/chave-publica-v{versao}", cache_segundos=0)
        resumo = RecifrarCampos(
            _repositorio(), DecifradorSealedBox(_chave_privada), CifradorSealedBox(publica, versao)
        ).executar()
        if resumo["falhas"] == 0:
            # remove as chaves privadas antigas somente apos recifrar
            # tudo com sucesso
            ssm = boto3.client("ssm")
            for antiga in evento.get("versoesAntigas", []):
                try:
                    ssm.delete_parameter(
                        Name=f"{parametros.prefixo()}/segredos/pii-chave-privada-v{int(antiga)}"
                    )
                except ssm.exceptions.ParameterNotFound:
                    continue
        return resumo
    raise ValueError(f"acao desconhecida: {acao}")
