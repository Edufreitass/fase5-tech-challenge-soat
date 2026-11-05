"""Validacao e formatacao de CPF."""

import re

_NAO_DIGITO = re.compile(r"\D")


def somente_digitos(valor: str) -> str:
    return _NAO_DIGITO.sub("", valor)


def cpf_valido(cpf: str) -> bool:
    digitos = somente_digitos(cpf)
    if len(digitos) != 11 or len(set(digitos)) == 1:  # noqa: PLR2004
        return False
    for tamanho in (9, 10):
        soma = sum(
            int(d) * p for d, p in zip(digitos[:tamanho], range(tamanho + 1, 1, -1), strict=True)
        )
        digito = (soma * 10) % 11 % 10
        if digito != int(digitos[tamanho]):
            return False
    return True
