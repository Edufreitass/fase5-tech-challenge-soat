from typing import Any, Protocol

from sales.domain.models import (
    Ator,
    DadosPagamento,
    EventoVenda,
    MotivoCancelamento,
    StatusVenda,
    Venda,
)
from shared.contracts import Cursor, DocumentacaoRetirada, EntradaSaga, ValidacaoComprador


class LeituraVenda(Protocol):
    """Leitura pontual e historico da venda."""

    def obter(self, venda_id: str) -> Venda | None: ...

    def historico(self, venda_id: str) -> list[EventoVenda]: ...


class ListagemVendas(Protocol):
    """Consultas paginadas para clientes e funcionarios."""

    def listar_por_status(
        self, status: StatusVenda, *, limite: int, cursor: Cursor | None
    ) -> tuple[list[Venda], Cursor | None]:
        """Mais recentes primeiro (gsi_status)."""
        ...

    def listar_do_cliente(
        self, cliente_id: str, *, limite: int, cursor: Cursor | None
    ) -> tuple[list[Venda], Cursor | None]:
        """Historico de compras do cliente, mais recentes primeiro
        (gsi_cliente).
        """
        ...


class ReservaVendas(LeituraVenda, Protocol):
    """Criacao e reserva atomica de uma compra."""

    def criar(self, venda: Venda, evento: EventoVenda) -> None: ...

    def reservar(self, venda: Venda, versao_veiculo: int, expira_em: str, agora: str) -> None:
        """Fase 2 atomica. Levanta `VeiculoIndisponivel`
        ou
        `ReservaAtivaExistente`.
        """
        ...

    def cancelar_por_conflito(self, venda_id: str, agora: str) -> None: ...


class InteracaoCompra(LeituraVenda, Protocol):
    """Operacoes do cliente e vendedor sobre a compra."""

    def solicitar_desistencia(self, venda_id: str) -> bool:
        """Persiste a desistencia antes do callback.

        Compete com a retirada, mesmo quando ja existe token.
        """
        ...

    def registrar_retirada(
        self, venda_id: str, retirada_em: str, documentacao: DocumentacaoRetirada
    ) -> bool: ...


class CicloVenda(LeituraVenda, Protocol):
    """Persistencia dos passos e recuperacao da saga."""

    def transicionar(  # noqa: PLR0913
        self,
        venda_id: str,
        de: StatusVenda,
        para: StatusVenda,
        *,
        agora: str,
        ator: Ator,
        motivo: MotivoCancelamento | None = None,
        definir: dict[str, Any] | None = None,
        remover: tuple[str, ...] = (),
    ) -> None:
        """`de -> para` condicional + evento; ja em `para` = sucesso
        (idempotente).
        """
        ...

    def liberar_lock(self, cliente_id: str, venda_id: str) -> None: ...

    def registrar_token(self, venda_id: str, etapa: str, token: str) -> bool:
        """False se a desistencia ja foi solicitada (a saga deve falhar
        a etapa).
        """
        ...

    def encerrar_retirada(self, venda_id: str) -> bool:
        """Fecha a janela; True se a retirada ja foi gravada."""
        ...

    def definir_saga(self, venda_id: str, execution_arn: str) -> None: ...

    def pendentes_de_saga(self, antes_de: str) -> list[Venda]: ...

    def criados_antigos(self, antes_de: str) -> list[Venda]: ...


class RepositorioVendas(ReservaVendas, ListagemVendas, InteracaoCompra, CicloVenda, Protocol):
    """Contrato completo do adaptador; cada caso de uso depende de uma
    porta menor.
    """


class LeitorPagamento(Protocol):
    def por_id(self, pagamento_id: str) -> DadosPagamento | None: ...


class ClientesInterno(Protocol):
    def validar_comprador(self, cliente_id: str) -> ValidacaoComprador: ...


class Saga(Protocol):
    def iniciar(self, entrada: EntradaSaga, nome: str) -> str:
        """StartExecution idempotente (nome = vendaId); retorna o
        executionArn.
        """
        ...

    def enviar_sucesso(self, token: str, saida: dict[str, Any]) -> bool: ...

    def enviar_falha(self, token: str, erro: str, causa: str) -> bool:
        """False se o token ja foi consumido/expirou."""
        ...
