"""Leitura de parametros do SSM Parameter Store com cache em memoria."""

import os
from functools import lru_cache

from aws_lambda_powertools.utilities import parameters

from shared.errors import SistemaNaoInicializado


def prefixo() -> str:
    return os.environ.get("SSM_PREFIXO", "/revenda/dev")


def obter(nome: str, *, segredo: bool = False, cache_segundos: int = 300) -> str:
    """Le `<prefixo>/<nome>`; parametro ausente indica migracoes ainda
    nao
    aplicadas.
    """
    try:
        valor = parameters.get_parameter(
            f"{prefixo()}/{nome}", decrypt=segredo, max_age=cache_segundos
        )
    except parameters.exceptions.GetParameterError as erro:
        raise SistemaNaoInicializado("Migracoes ainda nao aplicadas.") from erro
    return str(valor)


@lru_cache(maxsize=1)
def segredo_cursor() -> bytes:
    return obter("segredos/cursor-hmac", segredo=True).encode()
