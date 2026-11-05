"""Protege as fronteiras hexagonais, inclusive atraves de modulos
compartilhados."""

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"


def nome_modulo(arquivo: Path) -> str:
    partes = arquivo.relative_to(SRC).with_suffix("").parts
    return ".".join(partes[:-1] if partes[-1] == "__init__" else partes)


def dependencias(arquivo: Path) -> set[str]:
    modulo = nome_modulo(arquivo)
    pacote = modulo if arquivo.name == "__init__.py" else modulo.rpartition(".")[0]
    resultado: set[str] = set()
    for no in ast.walk(ast.parse(arquivo.read_text())):
        if isinstance(no, ast.Import):
            resultado.update(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom):
            base = no.module or ""
            if no.level:
                prefixo = pacote.split(".")[: len(pacote.split(".")) - no.level + 1]
                base = ".".join([*prefixo, *([base] if base else [])])
            resultado.add(base)
            # Inclui `from shared import crypto`, alem de `import
            # shared.crypto`.
            resultado.update(f"{base}.{alias.name}" for alias in no.names)
    return resultado


def caminhos_proibidos(
    origem: str, grafo: dict[str, set[str]], camada: str
) -> Iterator[list[str]]:
    internos = {modulo.split(".")[0] for modulo in grafo}
    pendentes = [[origem]]
    visitados: set[str] = set()
    while pendentes:
        caminho = pendentes.pop()
        modulo = caminho[-1]
        if modulo in visitados:
            continue
        visitados.add(modulo)
        partes = modulo.split(".")
        externo = partes[0] not in internos | sys.stdlib_module_names
        proibido = "adapters" in partes or (camada == "domain" and "application" in partes)
        if externo or proibido:
            yield caminho
            continue
        for destino in grafo.get(modulo, set()):
            pendentes.append([*caminho, destino])
            # Importar um submodulo tambem executa os __init__.py dos
            # pacotes.
            for indice in range(1, len(destino.split("."))):
                pacote = ".".join(destino.split(".")[:indice])
                if pacote in grafo:
                    pendentes.append([*caminho, pacote])


@pytest.mark.parametrize("camada", ["domain", "application"])
def test_nucleo_independente_de_infraestrutura(camada: str) -> None:
    grafo = {nome_modulo(arquivo): dependencias(arquivo) for arquivo in SRC.rglob("*.py")}
    violacoes = [
        " -> ".join(caminho)
        for modulo in grafo
        if camada in modulo.split(".")
        for caminho in caminhos_proibidos(modulo, grafo, camada)
    ]
    assert not violacoes, "\n".join(violacoes)


def test_detecta_dependencia_indireta_e_ciclos() -> None:
    grafo = {
        "customers.application.rotation": {"shared.crypto"},
        "shared.crypto": {"shared.errors", "nacl.public"},
        "shared.errors": {"shared.crypto"},
    }
    assert list(caminhos_proibidos("customers.application.rotation", grafo, "application")) == [
        ["customers.application.rotation", "shared.crypto", "nacl.public"]
    ]


@pytest.mark.parametrize(
    ("camada", "destino"),
    [
        ("domain", "sales.application.purchase"),
        ("domain", "sales.adapters.dynamodb.repository"),
        ("application", "sales.adapters.dynamodb.repository"),
    ],
)
def test_detecta_inversao_entre_camadas(camada: str, destino: str) -> None:
    origem = f"sales.{camada}.models"
    grafo = {origem: {destino}, destino: set()}
    assert list(caminhos_proibidos(origem, grafo, camada)) == [[origem, destino]]


def test_detecta_importacao_de_submodulo_por_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys.modules[__name__], "SRC", tmp_path)
    arquivo = tmp_path / "exemplo.py"
    arquivo.write_text("from shared import crypto as cripto\n")
    assert dependencias(arquivo) == {"shared", "shared.crypto"}


def test_resolve_importacao_relativa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.modules[__name__], "SRC", tmp_path)
    pacote = tmp_path / "sales" / "application"
    pacote.mkdir(parents=True)
    arquivo = pacote / "purchase.py"
    arquivo.write_text("from ..adapters import aws\n")
    assert dependencias(arquivo) == {"sales.adapters", "sales.adapters.aws"}
