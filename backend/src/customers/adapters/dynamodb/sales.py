"""Leitura das vendas do cliente (tabela `vendas`, somente leitura):
lock,
historico e concluidas.
"""

from typing import Any

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

_SER = TypeSerializer()
_DES = TypeDeserializer()


class VendasEmAndamentoDynamo:
    def __init__(self, cliente: Any, tabela_vendas: str) -> None:
        self._ddb = cliente
        self._tabela = tabela_vendas

    def possui(self, cliente_id: str) -> bool:
        chave = {
            "pk": _SER.serialize(f"CLIENTE#{cliente_id}"),
            "sk": _SER.serialize("RESERVA_ATIVA"),
        }
        return "Item" in self._ddb.get_item(TableName=self._tabela, Key=chave, ConsistentRead=True)

    em_andamento = possui

    def todas(self, cliente_id: str) -> list[dict[str, Any]]:
        itens: list[dict[str, Any]] = []
        inicio: dict[str, Any] | None = None
        while True:
            parametros: dict[str, Any] = {
                "TableName": self._tabela,
                "IndexName": "gsi_cliente",
                "KeyConditionExpression": "gsi1pk = :p",
                "ExpressionAttributeValues": {":p": _SER.serialize(f"CLIENTE#{cliente_id}")},
            }
            if inicio:
                parametros["ExclusiveStartKey"] = inicio
            r = self._ddb.query(**parametros)
            for bruto in r["Items"]:
                i = {k: _DES.deserialize(v) for k, v in bruto.items()}
                itens.append(
                    {
                        "id": i["id"],
                        "status": i["status"],
                        "veiculo": i.get("veiculoSnapshot"),
                        "precoNegociadoCentavos": int(i["precoNegociadoCentavos"]),
                        "criadoEm": i["criadoEm"],
                        "atualizadoEm": i["atualizadoEm"],
                        "motivoCancelamento": i.get("motivoCancelamento"),
                    }
                )
            inicio = r.get("LastEvaluatedKey")
            if not inicio:
                return itens

    def concluidas(self, cliente_id: str) -> list[tuple[str, str]]:
        return [
            (v["id"], v["atualizadoEm"])
            for v in self.todas(cliente_id)
            if v["status"] == "CONCLUIDO"
        ]
