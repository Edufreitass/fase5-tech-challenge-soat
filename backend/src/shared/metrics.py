"""Metricas de negocio via EMF (namespace `Revenda`, dimensao unica
`service`)

Sao exatamente 9 metricas, todas sob um unico valor de `service`, para
ficar dentro das 10
metricas customizadas do free tier. Novas metricas exigem revisar
esse teto."""

from aws_lambda_powertools import Metrics
from aws_lambda_powertools.metrics import MetricUnit

SERVICO = "revenda"
RESERVAS_CRIADAS = "ReservasCriadas"
RESERVAS_CONFLITO = "ReservasConflito"
VENDAS_CONCLUIDAS = "VendasConcluidas"
VENDAS_CANCELADAS = "VendasCanceladas"
VENDAS_ESTORNADAS = "VendasEstornadas"
PAGAMENTOS_TARDIOS = "PagamentosTardios"
WEBHOOK_SUSPEITO = "WebhookSuspeito"
ACESSOS_DADOS_PESSOAIS = "AcessosDadosPessoais"
DYNAMODB_THROTTLING = "DynamoDBThrottling"

NOMES = frozenset(
    {
        RESERVAS_CRIADAS,
        RESERVAS_CONFLITO,
        VENDAS_CONCLUIDAS,
        VENDAS_CANCELADAS,
        VENDAS_ESTORNADAS,
        PAGAMENTOS_TARDIOS,
        WEBHOOK_SUSPEITO,
        ACESSOS_DADOS_PESSOAIS,
        DYNAMODB_THROTTLING,
    }
)
LIMITE_FREE_TIER = 10

_metricas = Metrics(namespace="Revenda", service=SERVICO)

_POR_STATUS_FINAL = {
    "CONCLUIDO": VENDAS_CONCLUIDAS,
    "CANCELADO": VENDAS_CANCELADAS,
    "ESTORNADO": VENDAS_ESTORNADAS,
}


def emitir(nome: str, valor: float = 1) -> None:
    """Emite a metrica na hora (uma linha EMF no log); nome fora da
    lista e
    erro de programacao.
    """
    if nome not in NOMES:
        raise ValueError(f"metrica desconhecida: {nome}")
    _metricas.add_metric(name=nome, unit=MetricUnit.Count, value=valor)
    _metricas.flush_metrics()


def emitir_status_final_de_venda(status: str) -> None:
    nome = _POR_STATUS_FINAL.get(status)
    if nome:
        emitir(nome)
