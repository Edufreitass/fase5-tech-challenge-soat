"""Caso de uso `CadastrarVeiculo`, compartilhado pela API e
pelas
migracoes.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from shared.ids import novo_id
from shared.text import normalizar_busca
from shared.time import agora_iso
from vehicles.domain.models import NovoVeiculo, StatusVeiculo, Veiculo
from vehicles.domain.ports import RepositorioVeiculos
from vehicles.domain.validation import preco_para_centavos, validar_e_normalizar


@dataclass
class CadastrarVeiculo:
    repositorio: RepositorioVeiculos
    gerar_id: Callable[[], str] = field(default=novo_id)
    relogio: Callable[[], str] = field(default=agora_iso)

    def executar(self, novo: NovoVeiculo, criado_por: str) -> Veiculo:
        dados = validar_e_normalizar(novo)
        agora = self.relogio()
        veiculo = Veiculo(
            id=self.gerar_id(),
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
            status=StatusVeiculo.DISPONIVEL,
            versao=1,
            criado_em=agora,
            atualizado_em=agora,
            criado_por=criado_por,
        )
        self.repositorio.criar(veiculo)
        return veiculo
