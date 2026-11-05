"""Normalizacao de texto de entrada e de busca."""

import re
import unicodedata

_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")


def normalizar_texto(valor: str) -> str:
    """NFC, trim e remocao de caracteres de controle."""
    return _CONTROLE.sub("", unicodedata.normalize("NFC", valor)).strip()


def normalizar_busca(valor: str) -> str:
    """Minusculas e sem acento, para a busca por `contains`."""
    base = unicodedata.normalize("NFKD", valor.lower())
    return "".join(c for c in base if not unicodedata.combining(c))
