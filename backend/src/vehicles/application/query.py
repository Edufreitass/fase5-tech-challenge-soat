"""Consultas publicas do catalogo."""

from dataclasses import dataclass

from shared.contracts import Cursor
from shared.errors import RecursoNaoEncontrado
from vehicles.domain.models import FiltroVeiculos, StatusVeiculo, Veiculo
from vehicles.domain.ports import RepositorioVeiculos


@dataclass
class ConsultarVeiculos:
    repositorio: RepositorioVeiculos

    def listar(
        self,
        status: StatusVeiculo,
        *,
        limite: int,
        cursor: Cursor | None,
        filtro: FiltroVeiculos | None = None,
    ) -> tuple[list[Veiculo], Cursor | None]:
        return self.repositorio.listar_por_status(
            status, limite=limite, cursor=cursor, filtro=filtro
        )

    def listar_disponiveis(
        self, *, limite: int, cursor: Cursor | None, filtro: FiltroVeiculos | None = None
    ) -> tuple[list[Veiculo], Cursor | None]:
        return self.listar(StatusVeiculo.DISPONIVEL, limite=limite, cursor=cursor, filtro=filtro)

    def obter_completo(self, veiculo_id: str) -> Veiculo:
        """Visao de gestao (inclui INATIVO e campos internos)."""
        veiculo = self.repositorio.obter(veiculo_id)
        if veiculo is None:
            raise RecursoNaoEncontrado("Veiculo nao encontrado.")
        return veiculo

    def obter_publico(self, veiculo_id: str) -> Veiculo:
        veiculo = self.repositorio.obter(veiculo_id)
        if veiculo is None or veiculo.status == StatusVeiculo.INATIVO:
            raise RecursoNaoEncontrado("Veiculo nao encontrado.")
        return veiculo
