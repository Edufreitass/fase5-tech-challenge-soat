"""Mascaramento de dados pessoais para logs e respostas."""

import re
from typing import Any

CAMPOS_SENSIVEIS = frozenset(
    {
        "cpf",
        "rg",
        "cnh",
        "email",
        "telefone",
        "endereco",
        "nomecompleto",
        "nome",
        "authorization",
        "pixcopiaecola",
        "password",
        "senha",
        "tasktoken",
    }
)
MASCARA = "***"

_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_BEARER = re.compile(r"(?i)bearer\s+[\w.~+/=-]+")


def sanitizar_texto(texto: str) -> str:
    texto = _BEARER.sub("Bearer ***", texto)
    texto = _EMAIL.sub(MASCARA, texto)
    return _CPF.sub(MASCARA, texto)


def sanitizar(valor: Any) -> Any:
    """Mascara recursivamente chaves sensiveis e padroes de CPF/e-mail
    em
    strings.
    """
    if isinstance(valor, dict):
        return {
            chave: MASCARA
            if isinstance(chave, str) and chave.lower() in CAMPOS_SENSIVEIS
            else sanitizar(item)
            for chave, item in valor.items()
        }
    if isinstance(valor, list | tuple):
        return [sanitizar(item) for item in valor]
    if isinstance(valor, str):
        return sanitizar_texto(valor)
    return valor


def mascarar_cpf(ultimos5: str) -> str:
    """``***.***.123-45`` a partir dos 5 ultimos digitos."""
    return f"***.***.{ultimos5[:3]}-{ultimos5[3:]}"
