"""Passos da saga sobre o veiculo (fn-veiculos-worker)."""

from collections.abc import Callable
from dataclasses import dataclass, field

from shared.errors import EstadoInvalido
from shared.time import agora_iso
from vehicles.domain.ports import TransicoesSaga


@dataclass
class PassosVeiculo:
    repositorio: TransicoesSaga
    relogio: Callable[[], str] = field(default=agora_iso)

    def executar(self, acao: str, veiculo_id: str, venda_id: str) -> None:
        agora = self.relogio()
        if acao == "LIBERAR_VEICULO":
            self.repositorio.liberar(veiculo_id, venda_id, agora)
        elif acao == "AGUARDANDO_RETIRADA":
            if not self.repositorio.aguardar_retirada(veiculo_id, venda_id, agora):
                raise EstadoInvalido("veiculo nao pode aguardar retirada")
        elif acao == "BAIXAR_VEICULO":
            if not self.repositorio.baixar(veiculo_id, venda_id, agora):
                raise EstadoInvalido("veiculo nao pode receber baixa")
        else:
            raise ValueError(f"acao desconhecida: {acao}")
