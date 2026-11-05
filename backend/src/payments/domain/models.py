import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from shared.errors import EstadoInvalido


class StatusPagamento(StrEnum):
    PENDENTE = "PENDENTE"
    APROVADO = "APROVADO"
    RECUSADO = "RECUSADO"
    EXPIRADO = "EXPIRADO"
    CANCELADO = "CANCELADO"
    ESTORNADO = "ESTORNADO"
    APROVADO_TARDIO = "APROVADO_TARDIO"


class TipoEvento(StrEnum):
    PAGAMENTO_APROVADO = "PAGAMENTO_APROVADO"
    PAGAMENTO_RECUSADO = "PAGAMENTO_RECUSADO"
    COBRANCA_EXPIRADA = "COBRANCA_EXPIRADA"
    ESTORNO_CONCLUIDO = "ESTORNO_CONCLUIDO"


class Resultado(StrEnum):
    PROCESSADO = "PROCESSADO"
    IGNORADO = "IGNORADO"
    REJEITADO = "REJEITADO"


_NAMESPACE = uuid.UUID("6f1d3c9e-2b7a-4c55-9a1e-0d2f4b6a8c10")


def pagamento_id_da_venda(venda_id: str) -> str:
    """Id deterministico: reexecucoes do passo da saga nao duplicam o
    pagamento."""
    return str(uuid.uuid5(_NAMESPACE, venda_id))


@dataclass(frozen=True)
class Pagamento:
    id: str
    venda_id: str
    pix_copia_e_cola: str
    valor_centavos: int
    status: StatusPagamento
    expira_em: str
    id_transacao_externa: str
    criado_em: str
    atualizado_em: str
    versao: int = 1
    task_token: str | None = None
    ultima_sequencia: int = 0
    estorno: dict[str, Any] | None = None
    metodo: str = "PIX"

    def requer_estorno(self) -> bool:
        if self.status == StatusPagamento.ESTORNADO or self.estorno is not None:
            return False
        if self.status not in (StatusPagamento.APROVADO, StatusPagamento.APROVADO_TARDIO):
            raise EstadoInvalido(f"pagamento {self.status} nao pode ser estornado")
        return True
