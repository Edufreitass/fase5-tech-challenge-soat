from dataclasses import dataclass, field
from enum import StrEnum

from shared.contracts import DocumentacaoRetirada, SnapshotVeiculo
from shared.errors import EstadoInvalido, RetiradaIndisponivel, VendaNaoCancelavel


class StatusVenda(StrEnum):
    CRIADO = "CRIADO"
    RESERVADO = "RESERVADO"
    AGUARDANDO_PAGAMENTO = "AGUARDANDO_PAGAMENTO"
    PAGO = "PAGO"
    CONCLUIDO = "CONCLUIDO"
    CANCELADO = "CANCELADO"
    ESTORNADO = "ESTORNADO"

    @property
    def final(self) -> bool:
        return self in {StatusVenda.CONCLUIDO, StatusVenda.CANCELADO, StatusVenda.ESTORNADO}


class MotivoCancelamento(StrEnum):
    EXPIRADO = "EXPIRADO"
    RECUSADO = "RECUSADO"
    DESISTENCIA = "DESISTENCIA"
    NAO_RETIRADO = "NAO_RETIRADO"
    CONFLITO_RESERVA = "CONFLITO_RESERVA"
    FALHA_SISTEMICA = "FALHA_SISTEMICA"


class Ator(StrEnum):
    CLIENTE = "CLIENTE"
    VENDEDOR = "VENDEDOR"
    SISTEMA = "SISTEMA"
    GATEWAY = "GATEWAY"


class Etapa(StrEnum):
    PAGAMENTO = "PAGAMENTO"
    RETIRADA = "RETIRADA"


# Transicoes validas da venda; CANCELADO/ESTORNADO sao
# terminais.
TRANSICOES: dict[StatusVenda, frozenset[StatusVenda]] = {
    StatusVenda.CRIADO: frozenset({StatusVenda.RESERVADO, StatusVenda.CANCELADO}),
    StatusVenda.RESERVADO: frozenset({StatusVenda.AGUARDANDO_PAGAMENTO, StatusVenda.CANCELADO}),
    StatusVenda.AGUARDANDO_PAGAMENTO: frozenset({StatusVenda.PAGO, StatusVenda.CANCELADO}),
    StatusVenda.PAGO: frozenset({StatusVenda.CONCLUIDO, StatusVenda.ESTORNADO}),
    StatusVenda.CONCLUIDO: frozenset(),
    StatusVenda.CANCELADO: frozenset(),
    StatusVenda.ESTORNADO: frozenset(),
}


def transicao_valida(de: StatusVenda, para: StatusVenda) -> bool:
    return para in TRANSICOES[de]


@dataclass(frozen=True)
class Venda:
    id: str
    cliente_id: str
    veiculo_id: str
    veiculo_snapshot: SnapshotVeiculo
    preco_negociado_centavos: int
    status: StatusVenda
    versao: int
    criado_em: str
    atualizado_em: str
    correlation_id: str
    reserva_expira_em: str | None = None
    retirada_limite_em: str | None = None
    retirada_em: str | None = None
    documentacao: DocumentacaoRetirada | None = None
    pagamento_id: str | None = None
    saga_execution_arn: str | None = None
    task_token: str | None = None
    etapa_espera: Etapa | None = None
    desistencia_solicitada: bool = False
    motivo_cancelamento: MotivoCancelamento | None = None

    def validar_transicao(self, de: StatusVenda, para: StatusVenda) -> None:
        """Aceita repeticoes validas; o repositorio ainda garante a
        condicao atomica."""
        if not transicao_valida(de, para) or self.status not in (de, para):
            raise EstadoInvalido(f"transicao {de} -> {para} invalida com a venda em {self.status}")

    def validar_desistencia(self) -> None:
        if self.status.final or self.retirada_em:
            raise VendaNaoCancelavel("A venda ja foi concluida ou encerrada.")

    def validar_retirada(self) -> None:
        if self.status != StatusVenda.PAGO:
            raise VendaNaoCancelavel("A retirada so pode ser confirmada com a venda PAGA.")
        if not self.task_token or self.etapa_espera is None:
            raise RetiradaIndisponivel(
                "A venda foi paga e a retirada sera liberada em instantes; tente novamente."
            )


@dataclass(frozen=True)
class EventoVenda:
    para: StatusVenda
    ator: Ator
    ocorrido_em: str
    de: StatusVenda | None = None
    motivo: MotivoCancelamento | None = None
    ator_id: str | None = None


@dataclass(frozen=True)
class DadosPagamento:
    """Visao do pagamento exibida na venda (preenchida depois da
    emissao
    do
    codigo).
    """

    id: str
    status: str
    pix_copia_e_cola: str
    valor_centavos: int
    expira_em: str
    metodo: str = "PIX"


@dataclass
class ResultadoReserva:
    venda: Venda
    historico: list[EventoVenda] = field(default_factory=list)
