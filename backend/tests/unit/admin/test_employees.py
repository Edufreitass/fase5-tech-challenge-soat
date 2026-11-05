from typing import Any

import pytest

from admin.application.employees import AdministrarFuncionarios
from admin.domain.models import Funcionario, GrupoFuncionario, PaginaFuncionarios
from shared.errors import RecursoNaoEncontrado, RegraNegocioViolada


class DiretorioFake:
    def __init__(self) -> None:
        self.dados: dict[str, Funcionario] = {
            "a1": Funcionario("a1", "Admin", "a@x.com", ("admin",), True, True)
        }

    def listar(self, *, grupo: Any, limite: int, proximo: Any) -> PaginaFuncionarios:
        return PaginaFuncionarios(list(self.dados.values()), None)

    def obter(self, funcionario_id: str) -> Funcionario:
        if funcionario_id not in self.dados:
            raise RecursoNaoEncontrado
        return self.dados[funcionario_id]

    def criar(self, *, nome: str, email: str, grupo: GrupoFuncionario) -> Funcionario:
        f = Funcionario("n1", nome, email, (grupo.value,), True, False)
        self.dados[f.id] = f
        return f

    def trocar_grupo(self, funcionario_id: str, grupo: GrupoFuncionario) -> None:
        f = self.dados[funcionario_id]
        self.dados[funcionario_id] = Funcionario(
            f.id, f.nome, f.email, (grupo.value,), f.ativo, f.mfa_configurado
        )

    def definir_ativo(self, funcionario_id: str, *, ativo: bool) -> None:
        f = self.dados[funcionario_id]
        self.dados[funcionario_id] = Funcionario(
            f.id, f.nome, f.email, f.grupos, ativo, f.mfa_configurado
        )


class EventosFake:
    def __init__(self) -> None:
        self.publicados: list[tuple[str, dict[str, Any]]] = []

    def publicar(self, tipo: str, dados: dict[str, Any]) -> None:
        self.publicados.append((tipo, dados))


@pytest.fixture
def casos() -> tuple[AdministrarFuncionarios, EventosFake]:
    eventos = EventosFake()
    return AdministrarFuncionarios(DiretorioFake(), eventos), eventos


def test_criar_audita_sem_dados_pessoais(
    casos: tuple[AdministrarFuncionarios, EventosFake],
) -> None:
    usecase, eventos = casos
    criado = usecase.criar(
        nome="V", email="v@x.com", grupo=GrupoFuncionario.VENDEDOR, ator_id="a1"
    )
    assert criado.grupos == ("vendedor",)
    tipo, dados = eventos.publicados[0]
    assert tipo == "AcaoAdministrativa"
    assert "v@x.com" not in str(dados)
    assert dados["recursoId"] == "n1"


def test_nao_pode_desativar_a_si_mesmo(casos: tuple[AdministrarFuncionarios, EventosFake]) -> None:
    usecase, _ = casos
    with pytest.raises(RegraNegocioViolada):
        usecase.atualizar("a1", grupo=None, ativo=False, ator_id="a1")


def test_atualizar_troca_grupo_e_desativa(
    casos: tuple[AdministrarFuncionarios, EventosFake],
) -> None:
    usecase, _ = casos
    usecase.criar(nome="V", email="v@x.com", grupo=GrupoFuncionario.VENDEDOR, ator_id="a1")
    f = usecase.atualizar("n1", grupo=GrupoFuncionario.ADMIN, ativo=False, ator_id="a1")
    assert f.grupos == ("admin",)
    assert f.ativo is False


def test_atualizar_inexistente(casos: tuple[AdministrarFuncionarios, EventosFake]) -> None:
    usecase, _ = casos
    with pytest.raises(RecursoNaoEncontrado):
        usecase.atualizar("zzz", grupo=None, ativo=True, ator_id="a1")


def test_listar_audita(casos: tuple[AdministrarFuncionarios, EventosFake]) -> None:
    usecase, eventos = casos
    assert len(usecase.listar(grupo=None, limite=20, proximo=None, ator_id="a1").itens) == 1
    assert eventos.publicados[0][1]["acao"] == "LISTAR_FUNCIONARIOS"
