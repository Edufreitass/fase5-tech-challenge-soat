"""Edicao e inativacao/reativacao do anuncio, com
concorrencia
otimista (If-Match).
"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from shared.errors import RecursoNaoEncontrado, VersaoDesatualizada
from shared.text import normalizar_busca
from shared.time import agora_iso
from vehicles.domain.models import (
    NovoVeiculo,
    StatusVeiculo,
    Veiculo,
)
from vehicles.domain.ports import RepositorioVeiculos
from vehicles.domain.validation import preco_para_centavos, validar_e_normalizar


def _como_novo(v: Veiculo, mudancas: dict[str, Any]) -> NovoVeiculo:
    base: dict[str, Any] = {
        "marca": v.marca,
        "modelo": v.modelo,
        "ano_fabricacao": v.ano_fabricacao,
        "ano_modelo": v.ano_modelo,
        "cor": v.cor,
        "preco": v.preco,
        "quilometragem": v.quilometragem,
        "renavam": v.renavam,
        "chassi": v.chassi,
        "placa": v.placa,
        "combustivel": v.combustivel,
        "cambio": v.cambio,
        "descricao": v.descricao,
    }
    return NovoVeiculo(**{**base, **mudancas})


def _carregar(repo: RepositorioVeiculos, veiculo_id: str, versao: int) -> Veiculo:
    atual = repo.obter(veiculo_id)
    if atual is None:
        raise RecursoNaoEncontrado("Veiculo nao encontrado.")
    if atual.versao != versao:
        raise VersaoDesatualizada("O veiculo foi alterado; releia e tente de novo.")
    return atual


@dataclass
class EditarVeiculo:
    repositorio: RepositorioVeiculos
    relogio: Callable[[], str] = field(default=agora_iso)

    def executar(self, veiculo_id: str, mudancas: dict[str, Any], versao_esperada: int) -> Veiculo:
        atual = _carregar(self.repositorio, veiculo_id, versao_esperada)
        atual.validar_edicao(mudancas)
        dados = validar_e_normalizar(_como_novo(atual, mudancas))
        novo = replace(
            atual,
            marca=dados.marca,
            marca_busca=normalizar_busca(dados.marca),
            modelo=dados.modelo,
            modelo_busca=normalizar_busca(dados.modelo),
            ano_fabricacao=dados.ano_fabricacao,
            ano_modelo=dados.ano_modelo,
            cor=dados.cor,
            preco_centavos=preco_para_centavos(dados.preco),
            quilometragem=dados.quilometragem,
            renavam=dados.renavam,
            chassi=dados.chassi,
            placa=dados.placa,
            combustivel=dados.combustivel,
            cambio=dados.cambio,
            descricao=dados.descricao,
            versao=atual.versao + 1,
            atualizado_em=self.relogio(),
        )
        if replace(novo, versao=atual.versao, atualizado_em=atual.atualizado_em) == atual:
            return atual  # nada mudou: idempotente, sem nova versao
        self.repositorio.atualizar(atual, novo)
        return novo


@dataclass
class AlterarAnuncio:
    repositorio: RepositorioVeiculos
    relogio: Callable[[], str] = field(default=agora_iso)

    def inativar(self, veiculo_id: str, versao_esperada: int) -> Veiculo:
        return self._mudar(
            veiculo_id, versao_esperada, StatusVeiculo.DISPONIVEL, StatusVeiculo.INATIVO
        )

    def reativar(self, veiculo_id: str, versao_esperada: int) -> Veiculo:
        return self._mudar(
            veiculo_id, versao_esperada, StatusVeiculo.INATIVO, StatusVeiculo.DISPONIVEL
        )

    def _mudar(
        self, veiculo_id: str, versao: int, de: StatusVeiculo, para: StatusVeiculo
    ) -> Veiculo:
        atual = _carregar(self.repositorio, veiculo_id, versao)
        atual.validar_alteracao_anuncio(de, para)
        agora = self.relogio()
        self.repositorio.alterar_status(atual, para, agora)
        return replace(atual, status=para, versao=atual.versao + 1, atualizado_em=agora)
