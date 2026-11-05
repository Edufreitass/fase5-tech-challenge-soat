"""Cursor de paginacao opaco: base64url(JSON) + HMAC-SHA256."""

import base64
import hashlib
import hmac
import json
from typing import cast

from shared.contracts import Cursor
from shared.errors import RequisicaoInvalida

LIMITE_PADRAO = 20
LIMITE_MAXIMO = 50


def validar_limite(bruto: str | None) -> int:
    if bruto is None:
        return LIMITE_PADRAO
    if not bruto.isdigit() or not 1 <= int(bruto) <= LIMITE_MAXIMO:
        raise RequisicaoInvalida(f"limit deve estar entre 1 e {LIMITE_MAXIMO}")
    return int(bruto)


def _assinar(segredo: bytes, corpo: bytes) -> bytes:
    return hmac.new(segredo, corpo, hashlib.sha256).digest()


def codificar(chave: object, segredo: bytes) -> str:
    corpo = json.dumps(chave, separators=(",", ":"), sort_keys=True).encode()
    pacote = _assinar(segredo, corpo) + corpo
    return base64.urlsafe_b64encode(pacote).decode().rstrip("=")


def decodificar(token: str, segredo: bytes) -> object:
    try:
        pacote = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        assinatura, corpo = pacote[:32], pacote[32:]
        if not hmac.compare_digest(assinatura, _assinar(segredo, corpo)):
            raise ValueError("assinatura")
        return cast(object, json.loads(corpo))
    except Exception as erro:
        raise RequisicaoInvalida("nextToken invalido") from erro


def decodificar_cursor(token: str, segredo: bytes) -> Cursor:
    chave = decodificar(token, segredo)
    if (
        not isinstance(chave, dict)
        or not chave
        or not all(
            isinstance(campo, str) and isinstance(valor, str) for campo, valor in chave.items()
        )
    ):
        raise RequisicaoInvalida("nextToken invalido")
    return chave


def decodificar_texto(token: str, segredo: bytes) -> str:
    valor = decodificar(token, segredo)
    if not isinstance(valor, str):
        raise RequisicaoInvalida("nextToken invalido")
    return valor
