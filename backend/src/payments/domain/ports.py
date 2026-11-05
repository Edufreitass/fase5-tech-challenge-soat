from typing import Any, Protocol

from payments.domain.models import Pagamento, StatusPagamento
from shared.contracts import DadosCobranca


class RepositorioPagamentos(Protocol):
    def criar(self, pagamento: Pagamento) -> None:
        """Grava o pagamento e o ponteiro `TX#` atomicamente; ja
        existente
        = sucesso.
        """
        ...

    def obter(self, pagamento_id: str) -> Pagamento | None: ...

    def por_transacao(self, id_transacao_externa: str) -> Pagamento | None: ...

    def transicionar(  # noqa: PLR0913
        self,
        pagamento_id: str,
        de: tuple[StatusPagamento, ...],
        para: StatusPagamento,
        *,
        agora: str,
        sequencia: int | None = None,
        extras: dict[str, Any] | None = None,
    ) -> bool:
        """Condicional em `status IN de`; False se a condicao falhou."""
        ...

    def registrar_estorno(self, pagamento_id: str, id_estorno: str, agora: str) -> bool: ...

    def concluir_estorno(self, pagamento_id: str, agora: str) -> None: ...


class Gateway(Protocol):
    def criar_cobranca(
        self, *, referencia: str, valor_centavos: int, nome: str, cpf: str, expira_em: str
    ) -> tuple[str, str]:
        """(idTransacaoExterna, pixCopiaECola). Idempotente por
        `referencia`.
        """
        ...

    def cancelar_cobranca(self, id_transacao_externa: str) -> None: ...

    def estornar(self, id_transacao_externa: str, valor_centavos: int) -> str: ...


class ClientesInterno(Protocol):
    def obter_dados_cobranca(self, cliente_id: str) -> DadosCobranca: ...
