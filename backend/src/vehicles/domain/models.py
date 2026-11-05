from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from shared.errors import RegraNegocioViolada


class StatusVeiculo(StrEnum):
    DISPONIVEL = "DISPONIVEL"
    RESERVADO = "RESERVADO"
    AGUARDANDO_RETIRADA = "AGUARDANDO_RETIRADA"
    VENDIDO = "VENDIDO"
    INATIVO = "INATIVO"


class Combustivel(StrEnum):
    GASOLINA = "GASOLINA"
    ETANOL = "ETANOL"
    FLEX = "FLEX"
    DIESEL = "DIESEL"
    HIBRIDO = "HIBRIDO"
    ELETRICO = "ELETRICO"
    GNV = "GNV"


class Cambio(StrEnum):
    MANUAL = "MANUAL"
    AUTOMATICO = "AUTOMATICO"
    CVT = "CVT"
    AUTOMATIZADO = "AUTOMATIZADO"


@dataclass(frozen=True)
class NovoVeiculo:
    """Dados de entrada do cadastro (preco em string decimal, como na
    API).
    """

    marca: str
    modelo: str
    ano_fabricacao: int
    ano_modelo: int
    cor: str
    preco: str
    quilometragem: int
    renavam: str
    chassi: str
    placa: str | None = None
    combustivel: Combustivel | None = None
    cambio: Cambio | None = None
    descricao: str | None = None


@dataclass(frozen=True)
class FiltroVeiculos:
    """Filtros opcionais da listagem. Precos em centavos;
    marca/modelo ja normalizados."""

    marca: str | None = None
    modelo: str | None = None
    ano_min: int | None = None
    ano_max: int | None = None
    preco_min_centavos: int | None = None
    preco_max_centavos: int | None = None


CAMPOS_EDITAVEIS = (
    "marca",
    "modelo",
    "ano_fabricacao",
    "ano_modelo",
    "cor",
    "preco",
    "quilometragem",
    "placa",
    "renavam",
    "chassi",
    "combustivel",
    "cambio",
    "descricao",
)
# Alterar estes campos de um veiculo reservado/aguardando retirada
# comprometeria a venda.
CAMPOS_BLOQUEADOS_COM_VENDA = frozenset({"preco", "chassi", "renavam"})


@dataclass(frozen=True)
class Veiculo:
    id: str
    marca: str
    marca_busca: str
    modelo: str
    modelo_busca: str
    ano_fabricacao: int
    ano_modelo: int
    cor: str
    preco_centavos: int
    quilometragem: int
    renavam: str
    chassi: str
    status: StatusVeiculo
    versao: int
    criado_em: str
    atualizado_em: str
    criado_por: str
    placa: str | None = None
    combustivel: Combustivel | None = None
    cambio: Cambio | None = None
    descricao: str | None = None
    venda_atual_id: str | None = None

    def validar_edicao(self, campos: Iterable[str]) -> None:
        if self.status == StatusVeiculo.VENDIDO:
            raise RegraNegocioViolada("Veiculo vendido nao pode ser editado.")
        alterados = set(campos)
        desconhecidos = alterados - set(CAMPOS_EDITAVEIS)
        if desconhecidos:
            raise RegraNegocioViolada(f"Campos nao editaveis: {sorted(desconhecidos)}")
        if (
            self.status in (StatusVeiculo.RESERVADO, StatusVeiculo.AGUARDANDO_RETIRADA)
            and CAMPOS_BLOQUEADOS_COM_VENDA & alterados
        ):
            raise RegraNegocioViolada(
                "Com o veiculo reservado ou aguardando retirada nao se altera"
                " preco, chassi nem RENAVAM."
            )

    def validar_alteracao_anuncio(self, de: StatusVeiculo, para: StatusVeiculo) -> None:
        if self.status != de:
            raise RegraNegocioViolada(f"So e possivel passar de {de.value} para {para.value}.")

    @property
    def preco(self) -> str:
        return formatar_preco(self.preco_centavos)

    @property
    def placa_mascarada(self) -> str | None:
        return f"{self.placa[:3]}****" if self.placa else None


def formatar_preco(centavos: int) -> str:
    return f"{centavos // 100}.{centavos % 100:02d}"
