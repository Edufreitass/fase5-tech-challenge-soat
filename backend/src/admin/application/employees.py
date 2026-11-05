"""Casos de uso de administracao de funcionarios."""

from dataclasses import dataclass

from admin.domain.models import Funcionario, GrupoFuncionario, PaginaFuncionarios
from admin.domain.ports import DiretorioFuncionarios, PublicadorEventos
from shared.errors import RegraNegocioViolada


@dataclass
class AdministrarFuncionarios:
    diretorio: DiretorioFuncionarios
    eventos: PublicadorEventos

    def _auditar(self, acao: str, ator_id: str, alvo_id: str) -> None:
        self.eventos.publicar(
            "AcaoAdministrativa", {"acao": acao, "atorId": ator_id, "recursoId": alvo_id}
        )

    def listar(
        self, *, grupo: GrupoFuncionario | None, limite: int, proximo: str | None, ator_id: str
    ) -> PaginaFuncionarios:
        pagina = self.diretorio.listar(grupo=grupo, limite=limite, proximo=proximo)
        self._auditar("LISTAR_FUNCIONARIOS", ator_id, "*")
        return pagina

    def criar(
        self, *, nome: str, email: str, grupo: GrupoFuncionario, ator_id: str
    ) -> Funcionario:
        funcionario = self.diretorio.criar(nome=nome, email=email, grupo=grupo)
        self._auditar("CRIAR_FUNCIONARIO", ator_id, funcionario.id)
        return funcionario

    def atualizar(
        self,
        funcionario_id: str,
        *,
        grupo: GrupoFuncionario | None,
        ativo: bool | None,
        ator_id: str,
    ) -> Funcionario:
        if ativo is False and funcionario_id == ator_id:
            raise RegraNegocioViolada("Um administrador nao pode desativar a propria conta.")
        self.diretorio.obter(funcionario_id)  # 404 se nao existir
        if grupo is not None:
            self.diretorio.trocar_grupo(funcionario_id, grupo)
        if ativo is not None:
            self.diretorio.definir_ativo(funcionario_id, ativo=ativo)
        self._auditar("ATUALIZAR_FUNCIONARIO", ator_id, funcionario_id)
        return self.diretorio.obter(funcionario_id)
