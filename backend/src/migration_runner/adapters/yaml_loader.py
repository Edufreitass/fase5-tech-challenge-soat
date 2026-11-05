"""Traduz o documento YAML para o modelo independente de formato."""

import hashlib

import yaml

from migration_runner.domain.models import Migracao, MigracaoInvalida, validar_documento


def carregar(nome_arquivo: str, conteudo: bytes) -> Migracao:
    try:
        documento = yaml.safe_load(conteudo)
    except (yaml.YAMLError, UnicodeError) as erro:
        raise MigracaoInvalida(f"{nome_arquivo}: YAML invalido") from erro
    return validar_documento(nome_arquivo, documento, hashlib.sha256(conteudo).hexdigest())
