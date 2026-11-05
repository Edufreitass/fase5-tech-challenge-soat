"""fn-auditoria: consome a fila `auditoria` (SNS -> SQS) e grava a
trilha
imutavel no log group dedicado
(retencao de 5 anos). Os eventos nao carregam dados pessoais; mesmo
assim o texto e sanitizado.
"""

import json
import os
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import boto3

from shared.logger import criar_logger
from shared.masking import sanitizar

logger = criar_logger("auditoria")


@lru_cache(maxsize=1)
def _logs() -> Any:
    return boto3.client("logs")


def registro_de_auditoria(evento: dict[str, Any], recebido_em: str) -> dict[str, Any]:
    """{quem, quando, acao, recurso, campos, justificativa,
    correlationId}
    + o evento original sanitizado.
    """
    dados = sanitizar(evento)
    return {
        "tipo": dados.get("tipo"),
        "quando": dados.get("ocorridoEm", recebido_em),
        "quem": dados.get("atorId") or dados.get("clienteId"),
        "acao": dados.get("acao") or dados.get("tipo"),
        "recurso": dados.get("recursoId") or dados.get("vendaId") or dados.get("clienteId"),
        "justificativa": dados.get("justificativa"),
        "correlationId": dados.get("correlationId"),
        "recebidoEm": recebido_em,
        **{
            k: v
            for k, v in dados.items()
            if k not in {"tipo", "ocorridoEm", "correlationId", "justificativa"}
        },
    }


def _garantir_fluxo(grupo: str, fluxo: str) -> None:
    logs = _logs()
    try:
        logs.create_log_stream(logGroupName=grupo, logStreamName=fluxo)
    except logs.exceptions.ResourceAlreadyExistsException:
        return


def handler(evento: dict[str, Any], _contexto: Any) -> dict[str, Any]:
    grupo = os.environ["AUDITORIA_LOG_GROUP"]
    agora = datetime.now(UTC)
    fluxo = agora.strftime("%Y-%m-%d")
    recebido_em = agora.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    falhas: list[dict[str, str]] = []
    mensagens: list[tuple[str, str]] = []
    for registro in evento.get("Records", []):
        try:
            corpo = json.loads(registro["body"])
            mensagens.append(
                (
                    registro["messageId"],
                    json.dumps(registro_de_auditoria(corpo, recebido_em), ensure_ascii=False),
                )
            )
        except Exception:
            logger.exception("evento de auditoria invalido")
            falhas.append({"itemIdentifier": registro["messageId"]})
    if mensagens:
        try:
            _garantir_fluxo(grupo, fluxo)
            _logs().put_log_events(
                logGroupName=grupo,
                logStreamName=fluxo,
                logEvents=[
                    {"timestamp": int(agora.timestamp() * 1000), "message": m}
                    for _, m in mensagens
                ],
            )
        except Exception:
            logger.exception("falha ao gravar a trilha de auditoria")
            falhas += [{"itemIdentifier": i} for i, _ in mensagens]
    return {"batchItemFailures": falhas}
