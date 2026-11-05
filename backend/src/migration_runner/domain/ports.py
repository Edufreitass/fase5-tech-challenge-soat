from typing import Any, Protocol


class RepositorioParametros(Protocol):
    """Parametros do SSM sob `/revenda/<ambiente>/`."""

    def existe(self, nome: str) -> bool: ...

    def ler(self, nome: str) -> str | None: ...

    def gravar(self, nome: str, valor: str, *, segredo: bool, sobrescrever: bool) -> bool:
        """Retorna False (sem erro) se `sobrescrever=False` e o
        parametro
        ja existe.
        """
        ...


class CadastroVeiculos(Protocol):
    def cadastrar(self, item: dict[str, Any]) -> None:
        """Cadastra pelo caso de uso `CadastrarVeiculo`; chassi
        existente =
        sucesso.
        """
        ...


class DiretorioFuncionarios(Protocol):
    def garantir_funcionario(self, *, email: str, nome: str, grupo: str) -> None:
        """Cria o funcionario e o associa ao grupo; existente =
        sucesso.
        """
        ...
