from dataclasses import dataclass
from enum import StrEnum


class GrupoFuncionario(StrEnum):
    VENDEDOR = "vendedor"
    ADMIN = "admin"


@dataclass(frozen=True)
class Funcionario:
    id: str
    nome: str
    email: str
    grupos: tuple[str, ...]
    ativo: bool
    mfa_configurado: bool


@dataclass(frozen=True)
class PaginaFuncionarios:
    itens: list[Funcionario]
    proximo: str | None
