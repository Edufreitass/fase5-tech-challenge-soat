"""fn-clientes-interno: unica (com fn-lgpd-worker) com acesso a chave
privada PII.

Invocada somente por outras Lambdas via `lambda:InvokeFunction` (sem
rota HTTP).
Operacoes: VALIDAR_COMPRADOR e OBTER_DADOS_COBRANCA (nunca persiste nem
loga o claro)."""

import os
from functools import lru_cache
from typing import Any

import boto3

from customers.adapters.crypto.fields import DecifradorSealedBox
from customers.adapters.dynamodb.repository import DynamoDBClienteRepository
from customers.application.query import (
    ExportarDadosTitular,
    ObterDadosCobranca,
    ObterDadosDocumentacao,
    ValidarComprador,
)
from shared import parameters as parametros
from shared.logger import criar_logger

logger = criar_logger("clientes-interno")


@lru_cache(maxsize=1)
def _repositorio() -> DynamoDBClienteRepository:
    return DynamoDBClienteRepository(boto3.client("dynamodb"), os.environ["CLIENTES_TABELA"])


def _chave_privada(versao: int) -> str:
    return parametros.obter(f"segredos/pii-chave-privada-v{versao}", segredo=True)


def handler(evento: dict[str, Any], _contexto: Any) -> object:
    operacao = evento.get("operacao")
    cliente_id = str(evento.get("clienteId", ""))
    logger.info("operacao interna", extra={"operacao": operacao})
    if operacao == "VALIDAR_COMPRADOR":
        return ValidarComprador(_repositorio()).executar(
            cliente_id, parametros.obter("params/versao-termo-vigente")
        )
    if operacao == "OBTER_DADOS_COBRANCA":
        return ObterDadosCobranca(_repositorio(), DecifradorSealedBox(_chave_privada)).executar(
            cliente_id
        )
    if operacao == "OBTER_DADOS_DOCUMENTACAO":
        return ObterDadosDocumentacao(
            _repositorio(), DecifradorSealedBox(_chave_privada)
        ).executar(cliente_id)
    if operacao == "EXPORTAR_DADOS":
        return ExportarDadosTitular(_repositorio(), DecifradorSealedBox(_chave_privada)).executar(
            cliente_id
        )
    raise ValueError(f"operacao desconhecida: {operacao}")
