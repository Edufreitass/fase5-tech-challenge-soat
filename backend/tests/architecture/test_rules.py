"""Regras de arquitetura: rota sem papel e dominio com boto3
reprovam."""

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
RAIZ = SRC.parents[1]
VERBOS = {"get", "post", "put", "patch", "delete", "route"}


def handlers() -> list[Path]:
    return sorted(SRC.glob("*/adapters/**/handler.py"))


@pytest.mark.parametrize("arquivo", handlers(), ids=lambda p: str(p.relative_to(SRC)))
def test_nenhuma_rota_registrada_sem_papel(arquivo: Path) -> None:
    arvore = ast.parse(arquivo.read_text())
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef):
            for dec in no.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr in VERBOS
                ):
                    pytest.fail(f"{arquivo.name}:{no.name} usa @app.{dec.func.attr} sem papel")


@pytest.mark.parametrize("camada", ["domain", "application"])
def test_dominio_e_aplicacao_sem_boto3(camada: str) -> None:
    for arquivo in SRC.glob(f"*/{camada}/**/*.py"):
        texto = arquivo.read_text()
        assert not re.search(r"^\s*(import|from)\s+(boto3|botocore)", texto, re.MULTILINE), arquivo


def test_nenhum_script_operacional_no_repositorio() -> None:
    """Sem .sh/.ps1/.bat/Makefile/notebooks."""
    proibidos = ("*.sh", "*.ps1", "*.bat", "Makefile", "*.ipynb")
    ignorar = {".venv", ".git", ".terraform", "node_modules"}
    for padrao in proibidos:
        achados = [p for p in RAIZ.rglob(padrao) if not ignorar & set(p.parts)]
        assert not achados, achados


def test_nenhum_dado_de_conta_versionado() -> None:
    """Sem ID de conta, ARN com conta ou e-mail literal."""
    ignorar = {
        ".venv",
        ".git",
        ".terraform",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".import_linter_cache",
        "node_modules",
        "dist",
        "coverage",
        "playwright-report",
        "test-results",
    }
    for arquivo in RAIZ.rglob("*"):
        if not arquivo.is_file() or ignorar & set(arquivo.parts) or arquivo.suffix in {".pyc"}:
            continue
        if (
            arquivo.name in {"test_regras.py", ".terraform.lock.hcl"}
            or "tests" in arquivo.parts
            or "tfstate" in arquivo.name
        ):
            continue
        texto = arquivo.read_text(errors="ignore")
        assert not re.search(r"arn:aws:[a-z0-9-]+:[a-z0-9-]*:\d{12}:", texto), arquivo


def test_so_interno_e_lgpd_worker_leem_a_chave_privada() -> None:
    """So fn-clientes-interno e fn-lgpd-worker decifram
    (`DecifradorSealedBox`) e leem
    `pii-chave-privada-*`. Migracoes e admin apenas GRAVAM a chave
    (PutParameter), nunca a leem."""
    decifram = {
        SRC / "customers" / "adapters" / "internal",
        SRC / "customers" / "adapters" / "data_protection",
    }
    gravam = decifram | {SRC / "migration_runner", SRC / "admin" / "adapters" / "aws"}
    for arquivo in SRC.rglob("*.py"):
        texto = arquivo.read_text()
        if arquivo.name != "fields.py" and not any(p in decifram for p in arquivo.parents):
            assert "DecifradorSealedBox" not in texto, arquivo
        if not any(p in gravam for p in arquivo.parents):
            assert "pii-chave-privada" not in texto, arquivo
