"""Erros de dominio/aplicacao, independentes de HTTP e de AWS.

O adaptador HTTP (`shared.http`) traduz cada um para
`application/problem+json`."""

from typing import Any


class ErroNegocio(Exception):
    """Base dos erros previstos pelas regras de negocio."""

    slug = "erro-interno"
    status = 500
    titulo = "Erro interno"

    def __init__(self, detalhe: str | None = None, **extras: Any) -> None:
        super().__init__(detalhe or self.titulo)
        self.detalhe = detalhe
        self.extras = extras


class RequisicaoInvalida(ErroNegocio):
    slug = "requisicao-invalida"
    status = 400
    titulo = "Requisicao invalida"


class NaoAutenticado(ErroNegocio):
    slug = "nao-autenticado"
    status = 401
    titulo = "Autenticacao necessaria"


class AcessoNegado(ErroNegocio):
    slug = "acesso-negado"
    status = 403
    titulo = "Acesso negado"


class RecursoNaoEncontrado(ErroNegocio):
    slug = "recurso-nao-encontrado"
    status = 404
    titulo = "Recurso nao encontrado"


class PerfilClienteInexistente(AcessoNegado):
    """Usuario autenticado que ainda nao chamou `POST /clientes`."""

    slug = "perfil-cliente-inexistente"
    titulo = "Cadastro de cliente inexistente"


class ConflitoUnicidade(ErroNegocio):
    slug = "conflito-unicidade"
    status = 409
    titulo = "Registro ja existe"


class ErroValidacao(ErroNegocio):
    """Erros de campo (`erros[]`), 422 `validacao`."""

    slug = "validacao"
    status = 422
    titulo = "Erro de validacao"

    def __init__(self, erros: list[dict[str, str]]) -> None:
        super().__init__(None, erros=erros)


class RegraNegocioViolada(ErroNegocio):
    slug = "regra-negocio-violada"
    status = 422
    titulo = "Regra de negocio violada"


class DependenciaIndisponivel(ErroNegocio):
    slug = "dependencia-indisponivel"
    status = 503
    titulo = "Dependencia indisponivel"


class SistemaNaoInicializado(ErroNegocio):
    slug = "sistema-nao-inicializado"
    status = 503
    titulo = "Sistema nao inicializado"


class VeiculoIndisponivel(ErroNegocio):
    slug = "veiculo-indisponivel"
    status = 409
    titulo = "Veiculo nao esta mais disponivel"


class ReservaAtivaExistente(ErroNegocio):
    slug = "reserva-ativa-existente"
    status = 409
    titulo = "Ja existe uma compra em andamento"


class VendaNaoCancelavel(ErroNegocio):
    slug = "venda-nao-cancelavel"
    status = 409
    titulo = "A venda nao pode mais ser cancelada"


class CadastroIncompleto(ErroNegocio):
    slug = "cadastro-incompleto"
    status = 422
    titulo = "Cadastro incompleto"


class ErroDecifragem(Exception):
    """Falha ao decifrar ou contexto divergente."""


class EstadoInvalido(Exception):
    """Erro nao recuperavel de transicao (a saga trata como falha de
    compensacao)."""


class LimiteExcedido(ErroNegocio):
    slug = "limite-excedido"
    status = 429
    titulo = "Limite de requisicoes excedido"


class RetiradaIndisponivel(ErroNegocio):
    slug = "retirada-indisponivel"
    status = 409
    titulo = "A retirada ainda nao pode ser confirmada"


class SagaNaoReprocessavel(ErroNegocio):
    slug = "saga-nao-reprocessavel"
    status = 409
    titulo = "A saga nao pode ser reprocessada"


class VersaoDesatualizada(ErroNegocio):
    slug = "versao-desatualizada"
    status = 412
    titulo = "A versao do recurso mudou"


class PrecondicaoObrigatoria(ErroNegocio):
    slug = "precondicao-obrigatoria"
    status = 428
    titulo = "Cabecalho If-Match obrigatorio"
