"""Modelo das migracoes: arquivo YAML declarativo com catalogo fechado
de
operacoes.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from shared.errors import RequisicaoInvalida

PADRAO_ARQUIVO = re.compile(r"^V(\d{3})__([a-z0-9_]+)\.yml$")
PADRAO_PARAM = re.compile(r"\$\{param:([a-z0-9-]+)\}")

# operacao -> parametros obrigatorios (catalogo fechado)
CATALOGO: dict[str, frozenset[str]] = {
    "ssm.gerar_segredo": frozenset({"nome", "bytes"}),
    "ssm.gerar_par_chaves_pii": frozenset({"versao"}),
    "cognito.criar_funcionario": frozenset({"email", "nome", "grupo"}),
    "veiculos.cadastrar": frozenset({"itens"}),
}


class MigracaoInvalida(RequisicaoInvalida):
    titulo = "Migracao invalida"


@dataclass(frozen=True)
class Operacao:
    nome: str
    parametros: dict[str, Any]


@dataclass(frozen=True)
class Migracao:
    versao: int
    descricao: str
    checksum: str
    operacoes: list[Operacao] = field(default_factory=list)

    @property
    def chave(self) -> str:
        return f"V{self.versao:03d}"


def validar_documento(nome_arquivo: str, bruto: object, checksum: str) -> Migracao:
    """Valida nome, formato, catalogo e ausencia de valores sensiveis
    literais.
    """
    casado = PADRAO_ARQUIVO.match(nome_arquivo)
    if not casado:
        raise MigracaoInvalida(f"{nome_arquivo}: nome fora do padrao V<NNN>__<descricao>.yml")
    if not isinstance(bruto, dict) or set(bruto) != {"versao", "descricao", "operacoes"}:
        raise MigracaoInvalida(f"{nome_arquivo}: chaves devem ser versao, descricao e operacoes")
    if bruto["versao"] != int(casado.group(1)):
        raise MigracaoInvalida(f"{nome_arquivo}: versao difere do nome do arquivo")
    if not isinstance(bruto["operacoes"], list):
        raise MigracaoInvalida(f"{nome_arquivo}: operacoes deve ser lista")
    operacoes: list[Operacao] = []
    for item in bruto["operacoes"] or []:
        if not isinstance(item, dict):
            raise MigracaoInvalida(f"{nome_arquivo}: operacao deve ser objeto")
        nome = item.get("operacao")
        if not isinstance(nome, str) or nome not in CATALOGO:
            raise MigracaoInvalida(f"{nome_arquivo}: operacao fora do catalogo: {nome}")
        parametros = {k: v for k, v in item.items() if k != "operacao"}
        if set(parametros) != CATALOGO[nome]:
            raise MigracaoInvalida(
                f"{nome_arquivo}: parametros de {nome} devem ser {sorted(CATALOGO[nome])}"
            )
        if nome == "cognito.criar_funcionario" and not PADRAO_PARAM.fullmatch(
            str(parametros["email"])
        ):
            raise MigracaoInvalida(f"{nome_arquivo}: e-mail deve vir de ${{param:<nome>}}")
        if nome == "veiculos.cadastrar" and not (
            isinstance(parametros["itens"], list)
            and parametros["itens"]
            and all(isinstance(i, dict) for i in parametros["itens"])
        ):
            raise MigracaoInvalida(f"{nome_arquivo}: itens deve ser lista nao vazia de objetos")
        operacoes.append(Operacao(nome, parametros))
    return Migracao(
        versao=int(bruto["versao"]),
        descricao=str(bruto["descricao"]),
        checksum=checksum,
        operacoes=operacoes,
    )
