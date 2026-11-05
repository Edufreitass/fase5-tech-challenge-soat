"""Configuracao inicial: convida o administrador declarado na
implantacao.

Sem administrador cadastrado, nao ha quem convide a equipe. A rota e
publica, mas so cria o dono declarado em configuracao: a senha
temporaria segue apenas para a caixa de e-mail dele. Com um
administrador existente, o fluxo se fecha.
"""

from collections.abc import Callable
from dataclasses import dataclass

from admin.domain.models import Funcionario, GrupoFuncionario
from admin.domain.ports import DiretorioFuncionarios, PublicadorEventos
from shared.errors import ConflitoUnicidade

ATOR_CONFIGURACAO_INICIAL = "configuracao-inicial"
NOME_ADMINISTRADOR_INICIAL = "Administrador"


@dataclass
class ConfigurarPrimeiroAdministrador:
    diretorio: DiretorioFuncionarios
    eventos: PublicadorEventos
    email_dono: Callable[[], str]

    def necessaria(self) -> bool:
        pagina = self.diretorio.listar(grupo=GrupoFuncionario.ADMIN, limite=1, proximo=None)
        return not pagina.itens

    def executar(self) -> Funcionario:
        if not self.necessaria():
            raise ConflitoUnicidade("A configuracao inicial ja foi concluida.")
        criado = self.diretorio.criar(
            nome=NOME_ADMINISTRADOR_INICIAL, email=self.email_dono(), grupo=GrupoFuncionario.ADMIN
        )
        self.eventos.publicar(
            "AcaoAdministrativa",
            {
                "acao": "CONFIGURACAO_INICIAL",
                "atorId": ATOR_CONFIGURACAO_INICIAL,
                "recursoId": criado.id,
            },
        )
        return criado
