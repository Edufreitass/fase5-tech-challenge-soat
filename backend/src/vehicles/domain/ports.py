from typing import Protocol

from shared.contracts import Cursor
from vehicles.domain.models import FiltroVeiculos, StatusVeiculo, Veiculo


class RepositorioVeiculos(Protocol):
    def atualizar(self, atual: Veiculo, novo: Veiculo) -> None:
        """Substitui o veiculo se `versao`/`status` ainda forem os
        lidos;
        ajusta as chaves de
        unicidade. Levanta `VersaoDesatualizada` ou
        `ConflitoUnicidade`.
        """
        ...

    def alterar_status(self, atual: Veiculo, novo_status: StatusVeiculo, agora: str) -> None:
        """Condicional em `versao` e `status`; `VersaoDesatualizada` se
        divergir.
        """
        ...

    def criar(self, veiculo: Veiculo) -> None:
        """Grava o veiculo e as chaves de unicidade (chassi, RENAVAM,
        placa) atomicamente.

        Levanta `ConflitoUnicidade` se alguma ja existir.
        """
        ...

    def obter(self, veiculo_id: str) -> Veiculo | None: ...

    def listar_por_status(
        self,
        status: StatusVeiculo,
        *,
        limite: int,
        cursor: Cursor | None,
        filtro: FiltroVeiculos | None = None,
    ) -> tuple[list[Veiculo], Cursor | None]:
        """Ordenado por preco crescente (GSI). Retorna (itens,
        proxima_chave).
        """
        ...


class TransicoesSaga(Protocol):
    """Transicoes do veiculo executadas pela saga; todas
    idempotentes.
    """

    def liberar(self, veiculo_id: str, venda_id: str, agora: str) -> None: ...

    def aguardar_retirada(self, veiculo_id: str, venda_id: str, agora: str) -> bool: ...

    def baixar(self, veiculo_id: str, venda_id: str, agora: str) -> bool: ...
