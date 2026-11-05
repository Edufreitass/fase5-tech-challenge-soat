"""Publicador de eventos de dominio no SNS `revenda-eventos`."""

import json
from datetime import UTC, datetime
from typing import Any

from shared.ids import novo_id


class PublicadorSns:
    """Sem topico configurado, os eventos sao descartados."""

    def __init__(self, cliente: Any, topico_arn: str, correlation_id: str = "") -> None:
        self._sns = cliente
        self._topico = topico_arn
        self.correlation_id = correlation_id

    def publicar(self, tipo: str, dados: dict[str, Any]) -> None:
        if not self._topico:
            return
        corpo = {
            "versaoEvento": 1,
            "idEvento": novo_id(),
            "tipo": tipo,
            "ocorridoEm": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "correlationId": self.correlation_id,
            **dados,
        }
        self._sns.publish(
            TopicArn=self._topico,
            Message=json.dumps(corpo),
            MessageAttributes={"tipo": {"DataType": "String", "StringValue": tipo}},
        )
