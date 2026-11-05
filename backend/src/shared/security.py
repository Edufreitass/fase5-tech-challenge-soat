"""Autorizacao por papel a partir dos claims do Cognito Authorizer (API
Gateway REST)."""

import os
import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from shared.errors import AcessoNegado, NaoAutenticado


class Papel(StrEnum):
    ANONIMO = "anonimo"
    SISTEMA = "sistema"  # autenticado pelo API Gateway com IAM (SigV4), nao por JWT
    CLIENTE = "cliente"
    VENDEDOR = "vendedor"
    ADMIN = "admin"


def _pool_do_emissor(emissor: str) -> str:
    return emissor.rsplit("/", 1)[-1]


class Identidade:
    """Usuario autenticado, extraido dos claims validados pelo API
    Gateway.
    """

    def __init__(self, sub: str, grupos: frozenset[str], emissor: str, client_id: str) -> None:
        self.sub = sub
        self.grupos = grupos
        self.emissor = emissor
        self.client_id = client_id

    @property
    def funcionario(self) -> bool:
        return _pool_do_emissor(self.emissor) == os.environ.get("POOL_FUNCIONARIOS_ID", "-")

    @property
    def cliente(self) -> bool:
        return _pool_do_emissor(self.emissor) == os.environ.get("POOL_CLIENTES_ID", "-")


def _parse_grupos(bruto: Any) -> frozenset[str]:
    """O REST API entrega listas como string: ``[admin vendedor]``."""
    if not bruto:
        return frozenset()
    if isinstance(bruto, list | tuple):
        return frozenset(str(g) for g in bruto)
    return frozenset(g for g in re.split(r"[\s,]+", str(bruto).strip("[]")) if g)


def identidade_dos_claims(claims: Mapping[str, Any] | None) -> Identidade:
    if not claims or not claims.get("sub"):
        raise NaoAutenticado("Token ausente ou invalido.")
    if claims.get("token_use") != "access":
        raise NaoAutenticado("Use o access token.")
    identidade = Identidade(
        sub=str(claims["sub"]),
        grupos=_parse_grupos(claims.get("cognito:groups")),
        emissor=str(claims.get("iss", "")),
        client_id=str(claims.get("client_id", "")),
    )
    esperados = {
        os.environ.get("CLIENT_ID_CLIENTES", ""),
        os.environ.get("CLIENT_ID_FUNCIONARIOS", ""),
    } - {""}
    if esperados and identidade.client_id not in esperados:
        raise NaoAutenticado("Cliente OAuth nao reconhecido.")
    return identidade


def exigir_papel(identidade: Identidade, papeis: tuple[Papel, ...]) -> None:
    """Admin herda vendedor; cliente exige o pool de clientes;
    funcionario,
    o de funcionarios.
    """
    if Papel.CLIENTE in papeis and identidade.cliente:
        return
    if identidade.funcionario:
        if "admin" in identidade.grupos and (Papel.ADMIN in papeis or Papel.VENDEDOR in papeis):
            return
        if "vendedor" in identidade.grupos and Papel.VENDEDOR in papeis:
            return
    raise AcessoNegado("Papel insuficiente para este recurso.")
