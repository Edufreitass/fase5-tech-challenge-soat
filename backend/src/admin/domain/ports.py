from typing import Any, Protocol

from admin.domain.models import Funcionario, GrupoFuncionario, PaginaFuncionarios


class DiretorioFuncionarios(Protocol):
    """Porta para o diretorio de funcionarios (Cognito, pool de
    funcionarios).
    """

    def listar(
        self, *, grupo: GrupoFuncionario | None, limite: int, proximo: str | None
    ) -> PaginaFuncionarios: ...

    def obter(self, funcionario_id: str) -> Funcionario: ...

    def criar(self, *, nome: str, email: str, grupo: GrupoFuncionario) -> Funcionario: ...

    def trocar_grupo(self, funcionario_id: str, grupo: GrupoFuncionario) -> None: ...

    def definir_ativo(self, funcionario_id: str, *, ativo: bool) -> None: ...


class PublicadorEventos(Protocol):
    def publicar(self, tipo: str, dados: dict[str, Any]) -> None: ...
