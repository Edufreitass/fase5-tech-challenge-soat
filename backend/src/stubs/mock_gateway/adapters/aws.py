"""Adaptadores AWS do gateway simulado: DynamoDB (tabela gateway-
mock) e
SQS (mock-webhooks).
"""

import json
from typing import Any

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

_SER = TypeSerializer()
_DES = TypeDeserializer()
MAX_ATRASO_SQS = 900


def _ser(d: dict[str, Any]) -> dict[str, Any]:
    return {k: _SER.serialize(v) for k, v in d.items() if v is not None}


class DynamoDBMock:
    def __init__(self, cliente: Any, tabela: str) -> None:
        self._ddb = cliente
        self._tabela = tabela

    def obter_cobranca(self, tx: str) -> dict[str, Any] | None:
        r = self._ddb.get_item(
            TableName=self._tabela, Key=_ser({"pk": f"COBRANCA#{tx}"}), ConsistentRead=True
        )
        return {k: _DES.deserialize(v) for k, v in r["Item"].items()} if "Item" in r else None

    def _put(self, pk: str, dados: dict[str, Any]) -> bool:
        try:
            self._ddb.put_item(
                TableName=self._tabela,
                Item=_ser({"pk": pk, **dados}),
                ConditionExpression="attribute_not_exists(pk)",
            )
        except self._ddb.exceptions.ConditionalCheckFailedException:
            return False
        return True

    def salvar_cobranca(self, tx: str, dados: dict[str, Any]) -> bool:
        return self._put(f"COBRANCA#{tx}", dados)

    def salvar_estorno(self, estorno_id: str, dados: dict[str, Any]) -> bool:
        novo = self._put(f"ESTORNO#{estorno_id}", dados)
        if not novo:
            # Compatibilidade com registros criados antes do evento
            # persistido: a primeira tentativa define o payload estavel.
            self._ddb.update_item(
                TableName=self._tabela,
                Key=_ser({"pk": f"ESTORNO#{estorno_id}"}),
                UpdateExpression="SET evento = if_not_exists(evento, :e)",
                ExpressionAttributeValues=_ser({":e": dados["evento"]}),
            )
        return novo

    def obter_estorno(self, estorno_id: str) -> dict[str, Any]:
        r = self._ddb.get_item(
            TableName=self._tabela,
            Key=_ser({"pk": f"ESTORNO#{estorno_id}"}),
            ConsistentRead=True,
        )
        return {k: _DES.deserialize(v) for k, v in r["Item"].items()}

    def atualizar_status(self, tx: str, de: str, para: str) -> None:
        try:
            self._ddb.update_item(
                TableName=self._tabela,
                Key=_ser({"pk": f"COBRANCA#{tx}"}),
                UpdateExpression="SET #s = :p",
                ConditionExpression="#s = :d",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues=_ser({":p": para, ":d": de}),
            )
        except self._ddb.exceptions.ConditionalCheckFailedException:
            return


class FilaSqs:
    def __init__(self, cliente: Any, url: str) -> None:
        self._sqs = cliente
        self._url = url

    def enviar(self, mensagem: dict[str, Any], atraso_segundos: int) -> None:
        self._sqs.send_message(
            QueueUrl=self._url,
            MessageBody=json.dumps(mensagem),
            DelaySeconds=max(0, min(atraso_segundos, MAX_ATRASO_SQS)),
        )
