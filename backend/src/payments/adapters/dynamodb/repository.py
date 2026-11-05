"""Repositorio DynamoDB de pagamentos (tabela `pagamentos`, ponteiro
`TX#<idTransacaoExterna>`)."""

from typing import Any

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

from payments.domain.models import Pagamento, StatusPagamento
from shared.dynamo import transacionar
from shared.errors import EstadoInvalido

_SER = TypeSerializer()
_DES = TypeDeserializer()


def _serd(d: dict[str, Any]) -> dict[str, Any]:
    return {k: _SER.serialize(v) for k, v in d.items() if v is not None}


def _des(item: dict[str, Any]) -> dict[str, Any]:
    return {k: _DES.deserialize(v) for k, v in item.items()}


def _chave(pagamento_id: str) -> dict[str, Any]:
    return _serd({"pk": f"PAGAMENTO#{pagamento_id}", "sk": "META"})


def para_item(p: Pagamento) -> dict[str, Any]:
    return {
        "pk": f"PAGAMENTO#{p.id}",
        "sk": "META",
        "tipo": "PAGAMENTO",
        "id": p.id,
        "vendaId": p.venda_id,
        "metodo": p.metodo,
        "pixCopiaECola": p.pix_copia_e_cola,
        "valorCentavos": p.valor_centavos,
        "status": p.status.value,
        "expiraEm": p.expira_em,
        "idTransacaoExterna": p.id_transacao_externa,
        "versao": p.versao,
        "criadoEm": p.criado_em,
        "atualizadoEm": p.atualizado_em,
    }


def de_item(i: dict[str, Any]) -> Pagamento:
    ultimo = i.get("ultimoEventoGateway") or {}
    return Pagamento(
        id=i["id"],
        venda_id=i["vendaId"],
        pix_copia_e_cola=i["pixCopiaECola"],
        valor_centavos=int(i["valorCentavos"]),
        status=StatusPagamento(i["status"]),
        expira_em=i["expiraEm"],
        id_transacao_externa=i["idTransacaoExterna"],
        criado_em=i["criadoEm"],
        atualizado_em=i["atualizadoEm"],
        versao=int(i["versao"]),
        task_token=i.get("taskToken"),
        ultima_sequencia=int(ultimo.get("sequencia", 0)),
        estorno=i.get("estorno"),
        metodo=i.get("metodo", "PIX"),
    )


class DynamoDBPagamentoRepository:
    def __init__(self, cliente: Any, tabela: str) -> None:
        self._ddb = cliente
        self._tabela = tabela

    def criar(self, pagamento: Pagamento) -> None:
        try:
            transacionar(
                self._ddb,
                [
                    {
                        "Put": {
                            "TableName": self._tabela,
                            "Item": _serd(para_item(pagamento)),
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                    {
                        "Put": {
                            "TableName": self._tabela,
                            "Item": _serd(
                                {
                                    "pk": f"TX#{pagamento.id_transacao_externa}",
                                    "sk": "PONTEIRO",
                                    "pagamentoId": pagamento.id,
                                }
                            ),
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                ],
            )
        except self._ddb.exceptions.TransactionCanceledException:
            return  # reexecucao: ja criado

    def obter(self, pagamento_id: str) -> Pagamento | None:
        r = self._ddb.get_item(
            TableName=self._tabela, Key=_chave(pagamento_id), ConsistentRead=True
        )
        return de_item(_des(r["Item"])) if "Item" in r else None

    def por_transacao(self, id_transacao_externa: str) -> Pagamento | None:
        r = self._ddb.get_item(
            TableName=self._tabela,
            Key=_serd({"pk": f"TX#{id_transacao_externa}", "sk": "PONTEIRO"}),
        )
        if "Item" not in r:
            return None
        return self.obter(_des(r["Item"])["pagamentoId"])

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
        sets = ["#s = :para", "atualizadoEm = :t", "versao = versao + :um"]
        valores: dict[str, Any] = {":para": para.value, ":t": agora, ":um": 1}
        if sequencia is not None:
            sets.append("ultimoEventoGateway = :ult")
            valores[":ult"] = {"sequencia": sequencia, "ocorridoEm": agora}
        for i, (chave, valor) in enumerate((extras or {}).items()):
            sets.append(f"{chave} = :x{i}")
            valores[f":x{i}"] = valor
        condicao = " OR ".join(f"#s = :de{i}" for i in range(len(de)))
        valores.update({f":de{i}": s.value for i, s in enumerate(de)})
        try:
            self._ddb.update_item(
                TableName=self._tabela,
                Key=_chave(pagamento_id),
                UpdateExpression="SET " + ", ".join(sets),
                ConditionExpression=condicao,
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues=_serd(valores),
            )
        except self._ddb.exceptions.ConditionalCheckFailedException:
            return False
        return True

    def registrar_token(self, pagamento_id: str, token: str) -> None:
        self._ddb.update_item(
            TableName=self._tabela,
            Key=_chave(pagamento_id),
            UpdateExpression="SET taskToken = :t",
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeValues=_serd({":t": token}),
        )

    def registrar_estorno(self, pagamento_id: str, id_estorno: str, agora: str) -> bool:
        try:
            self._ddb.update_item(
                TableName=self._tabela,
                Key=_chave(pagamento_id),
                UpdateExpression="SET estorno = :e, atualizadoEm = :t",
                ConditionExpression="attribute_not_exists(estorno)",
                ExpressionAttributeValues=_serd(
                    {
                        ":e": {
                            "idEstornoExterno": id_estorno,
                            "status": "SOLICITADO",
                            "solicitadoEm": agora,
                        },
                        ":t": agora,
                    }
                ),
            )
        except self._ddb.exceptions.ConditionalCheckFailedException:
            return False
        return True

    def concluir_estorno(self, pagamento_id: str, agora: str) -> None:
        pg = self.obter(pagamento_id)
        if pg is None:
            raise EstadoInvalido("pagamento inexistente")
        estorno = dict(pg.estorno or {})
        estorno["status"] = "CONCLUIDO"
        self._ddb.update_item(
            TableName=self._tabela,
            Key=_chave(pagamento_id),
            UpdateExpression="SET #s = :e, estorno = :est, atualizadoEm = :t",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues=_serd({":e": "ESTORNADO", ":est": estorno, ":t": agora}),
        )
