"""Adaptador das migracoes para o caso de uso `CadastrarVeiculo`."""

import time
from typing import Any

from shared.errors import ConflitoUnicidade
from vehicles.application.registration import CadastrarVeiculo
from vehicles.domain.models import Cambio, Combustivel, NovoVeiculo

PAUSA_SEGUNDOS = 0.4  # a tabela e provisionada (free tier): evita rajada de escritas


class CadastroVeiculosMigracao:
    def __init__(self, caso_de_uso: CadastrarVeiculo, pausa: float = PAUSA_SEGUNDOS) -> None:
        self._caso = caso_de_uso
        self._pausa = pausa

    def cadastrar(self, item: dict[str, Any]) -> None:
        novo = NovoVeiculo(
            marca=item["marca"],
            modelo=item["modelo"],
            ano_fabricacao=item["anoFabricacao"],
            ano_modelo=item["anoModelo"],
            cor=item["cor"],
            preco=str(item["preco"]),
            quilometragem=item["quilometragem"],
            renavam=str(item["renavam"]),
            chassi=item["chassi"],
            placa=item.get("placa"),
            combustivel=Combustivel(item["combustivel"]) if item.get("combustivel") else None,
            cambio=Cambio(item["cambio"]) if item.get("cambio") else None,
            descricao=item.get("descricao"),
        )
        try:
            self._caso.executar(novo, criado_por="migracao")
        except ConflitoUnicidade:
            return  # ja cadastrado: idempotente
        time.sleep(self._pausa)
