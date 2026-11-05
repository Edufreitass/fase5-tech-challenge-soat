"""Repositorio DynamoDB de vendas (tabela `vendas`), com a reserva
atomica
entre `vendas` e `veiculos`.
"""

from typing import Any

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

from sales.domain.models import (
    Ator,
    Etapa,
    EventoVenda,
    MotivoCancelamento,
    StatusVenda,
    Venda,
)
from shared.contracts import Cursor, DocumentacaoRetirada
from shared.dynamo import transacionar
from shared.errors import EstadoInvalido, ReservaAtivaExistente, VeiculoIndisponivel

GSI_CLIENTE = "gsi_cliente"
GSI_STATUS = "gsi_status"
_SER = TypeSerializer()
_DES = TypeDeserializer()
CHAVE_FALHA_CONDICAO = "ConditionalCheckFailed"


def _ser(valor: Any) -> Any:
    return _SER.serialize(valor)


def _serd(d: dict[str, Any]) -> dict[str, Any]:
    return {k: _SER.serialize(v) for k, v in d.items() if v is not None}


def _des(item: dict[str, Any]) -> dict[str, Any]:
    return {k: _DES.deserialize(v) for k, v in item.items()}


def _pk(venda_id: str) -> dict[str, Any]:
    return _serd({"pk": f"VENDA#{venda_id}", "sk": "META"})


def _evento_item(venda_id: str, e: EventoVenda) -> dict[str, Any]:
    return {
        "pk": f"VENDA#{venda_id}",
        "sk": f"EVENTO#{e.ocorrido_em}#{e.para.value}",
        "tipo": "EVENTO_VENDA",
        "de": e.de.value if e.de else None,
        "para": e.para.value,
        "motivo": e.motivo.value if e.motivo else None,
        "ator": e.ator.value,
        "atorId": e.ator_id,
        "ocorridoEm": e.ocorrido_em,
    }


def _gsi_status(status: StatusVenda, criado_em: str, venda_id: str) -> tuple[str, str]:
    return f"STATUS#{status.value}", f"{criado_em}#{venda_id}"


def para_item(v: Venda) -> dict[str, Any]:
    g2 = _gsi_status(v.status, v.criado_em, v.id)
    return {
        "pk": f"VENDA#{v.id}",
        "sk": "META",
        "tipo": "VENDA",
        "id": v.id,
        "clienteId": v.cliente_id,
        "veiculoId": v.veiculo_id,
        "veiculoSnapshot": v.veiculo_snapshot,
        "precoNegociadoCentavos": v.preco_negociado_centavos,
        "status": v.status.value,
        "versao": v.versao,
        "criadoEm": v.criado_em,
        "atualizadoEm": v.atualizado_em,
        "correlationId": v.correlation_id,
        "gsi1pk": f"CLIENTE#{v.cliente_id}",
        "gsi1sk": f"{v.criado_em}#{v.id}",
        "gsi2pk": g2[0],
        "gsi2sk": g2[1],
    }


def de_item(i: dict[str, Any]) -> Venda:
    def inteiro(x: Any) -> int:
        return int(x)

    return Venda(
        id=i["id"],
        cliente_id=i["clienteId"],
        veiculo_id=i["veiculoId"],
        veiculo_snapshot=i["veiculoSnapshot"],
        preco_negociado_centavos=inteiro(i["precoNegociadoCentavos"]),
        status=StatusVenda(i["status"]),
        versao=inteiro(i["versao"]),
        criado_em=i["criadoEm"],
        atualizado_em=i["atualizadoEm"],
        correlation_id=i.get("correlationId", ""),
        reserva_expira_em=i.get("reservaExpiraEm"),
        retirada_limite_em=i.get("retiradaLimiteEm"),
        retirada_em=i.get("retiradaEm"),
        documentacao=i.get("documentacao"),
        pagamento_id=i.get("pagamentoId"),
        saga_execution_arn=i.get("sagaExecutionArn"),
        task_token=i.get("taskToken"),
        etapa_espera=Etapa(i["etapaEspera"]) if i.get("etapaEspera") else None,
        desistencia_solicitada=bool(i.get("desistenciaSolicitada", False)),
        motivo_cancelamento=MotivoCancelamento(i["motivoCancelamento"])
        if i.get("motivoCancelamento")
        else None,
    )


def de_evento(i: dict[str, Any]) -> EventoVenda:
    return EventoVenda(
        para=StatusVenda(i["para"]),
        ator=Ator(i["ator"]),
        ocorrido_em=i["ocorridoEm"],
        de=StatusVenda(i["de"]) if i.get("de") else None,
        motivo=MotivoCancelamento(i["motivo"]) if i.get("motivo") else None,
        ator_id=i.get("atorId"),
    )


class DynamoDBVendaRepository:
    def __init__(self, cliente: Any, tabela_vendas: str, tabela_veiculos: str) -> None:
        self._ddb = cliente
        self._vendas = tabela_vendas
        self._veiculos = tabela_veiculos

    # -- helpers
    # ---------------------------------------------------------------
    def _transacao(self, itens: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        """Executa a transacao; retorna os motivos de cancelamento ou
        None se ok.
        """
        try:
            transacionar(self._ddb, itens)
        except self._ddb.exceptions.TransactionCanceledException as erro:
            return list(erro.response.get("CancellationReasons", []))
        return None

    def _put(self, item: dict[str, Any], condicao: str | None = None) -> dict[str, Any]:
        put: dict[str, Any] = {"TableName": self._vendas, "Item": _serd(item)}
        if condicao:
            put["ConditionExpression"] = condicao
        return {"Put": put}

    def _update(
        self,
        venda_id: str,
        expressao: str,
        valores: dict[str, Any],
        condicao: str,
        nomes: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        atualizacao: dict[str, Any] = {
            "TableName": self._vendas,
            "Key": _pk(venda_id),
            "UpdateExpression": expressao,
            "ConditionExpression": condicao,
            "ExpressionAttributeValues": _serd(valores),
        }
        if nomes:
            atualizacao["ExpressionAttributeNames"] = nomes
        return {"Update": atualizacao}

    @staticmethod
    def _reprovou(motivos: list[dict[str, Any]], indice: int) -> bool:
        # TransactionConflict persistente (apos os retries) = outra
        # reserva do mesmo item em
        # andamento
        return indice < len(motivos) and motivos[indice].get("Code") in (
            CHAVE_FALHA_CONDICAO,
            "TransactionConflict",
        )

    # -- fase 1 e 2 da reserva
    # ---------------------------------------------------
    def criar(self, venda: Venda, evento: EventoVenda) -> None:
        motivos = self._transacao(
            [
                self._put(para_item(venda), "attribute_not_exists(pk)"),
                self._put(_evento_item(venda.id, evento)),
            ]
        )
        if motivos is not None:
            raise EstadoInvalido("venda ja existente")

    def reservar(self, venda: Venda, versao_veiculo: int, expira_em: str, agora: str) -> None:
        g2 = _gsi_status(StatusVenda.RESERVADO, venda.criado_em, venda.id)
        evento = EventoVenda(StatusVenda.RESERVADO, Ator.SISTEMA, agora, de=StatusVenda.CRIADO)
        veiculo = {
            "Update": {
                "TableName": self._veiculos,
                "Key": _serd({"pk": f"VEICULO#{venda.veiculo_id}", "sk": "META"}),
                "UpdateExpression": (
                    "SET #s = :res, versao = :vn, vendaAtualId = :vid, gsi1pk = :"
                    "g, atualizadoEm = :t"
                ),
                "ConditionExpression": "#s = :disp AND versao = :v",
                "ExpressionAttributeNames": {"#s": "status"},
                "ExpressionAttributeValues": _serd(
                    {
                        ":res": "RESERVADO",
                        ":vn": versao_veiculo + 1,
                        ":vid": venda.id,
                        ":g": "STATUS#RESERVADO",
                        ":t": agora,
                        ":disp": "DISPONIVEL",
                        ":v": versao_veiculo,
                    }
                ),
            }
        }
        lock = self._put(
            {
                "pk": f"CLIENTE#{venda.cliente_id}",
                "sk": "RESERVA_ATIVA",
                "vendaId": venda.id,
                "criadoEm": agora,
            },
            "attribute_not_exists(pk)",
        )
        atualizar = self._update(
            venda.id,
            (
                "SET #s = :r, reservaExpiraEm = :e, atualizadoEm = :t, versao"
                " = versao + :um, gsi2pk = :g2p"
            ),
            {
                ":r": "RESERVADO",
                ":e": expira_em,
                ":t": agora,
                ":um": 1,
                ":g2p": g2[0],
                ":c": "CRIADO",
            },
            "#s = :c",
            {"#s": "status"},
        )
        motivos = self._transacao(
            [veiculo, lock, atualizar, self._put(_evento_item(venda.id, evento))]
        )
        if motivos is None:
            return
        if self._reprovou(motivos, 0):
            raise VeiculoIndisponivel("O veiculo foi reservado por outro cliente.")
        if self._reprovou(motivos, 1):
            raise ReservaAtivaExistente("Voce ja possui uma compra em andamento.")
        raise EstadoInvalido(f"reserva falhou: {motivos}")

    def cancelar_por_conflito(self, venda_id: str, agora: str) -> None:
        self.transicionar(
            venda_id,
            StatusVenda.CRIADO,
            StatusVenda.CANCELADO,
            agora=agora,
            ator=Ator.SISTEMA,
            motivo=MotivoCancelamento.CONFLITO_RESERVA,
        )

    # -- leitura
    # ---------------------------------------------------------------
    def obter(self, venda_id: str) -> Venda | None:
        r = self._ddb.get_item(TableName=self._vendas, Key=_pk(venda_id), ConsistentRead=True)
        return de_item(_des(r["Item"])) if "Item" in r else None

    def historico(self, venda_id: str) -> list[EventoVenda]:
        r = self._ddb.query(
            TableName=self._vendas,
            ConsistentRead=True,
            KeyConditionExpression="pk = :p AND begins_with(sk, :e)",
            ExpressionAttributeValues=_serd({":p": f"VENDA#{venda_id}", ":e": "EVENTO#"}),
        )
        return [de_evento(_des(i)) for i in r["Items"]]

    # -- transicoes dos workers
    # --------------------------------------------------
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
        atual = self.obter(venda_id)
        if atual is None:
            raise EstadoInvalido("venda inexistente")
        atual.validar_transicao(de, para)
        if atual.status == para:
            return
        g2 = _gsi_status(para, atual.criado_em, venda_id)
        sets = ["#s = :para", "atualizadoEm = :t", "versao = versao + :um", "gsi2pk = :g2p"]
        valores: dict[str, Any] = {
            ":para": para.value,
            ":t": agora,
            ":um": 1,
            ":g2p": g2[0],
            ":de": de.value,
        }
        if motivo:
            sets.append("motivoCancelamento = :m")
            valores[":m"] = motivo.value
        for i, (chave, valor) in enumerate((definir or {}).items()):
            sets.append(f"{chave} = :d{i}")
            valores[f":d{i}"] = valor
        expressao = "SET " + ", ".join(sets) + (f" REMOVE {', '.join(remover)}" if remover else "")
        evento = EventoVenda(para, ator, agora, de=de, motivo=motivo)
        motivos = self._transacao(
            [
                self._update(venda_id, expressao, valores, "#s = :de", {"#s": "status"}),
                self._put(_evento_item(venda_id, evento)),
            ]
        )
        if motivos is None:
            return
        relida = self.obter(venda_id)
        if relida is not None and relida.status == para:
            return  # idempotente: ja esta no estado-alvo
        raise EstadoInvalido(
            f"transicao {de} -> {para} invalida com a venda em {relida and relida.status}"
        )

    def liberar_lock(self, cliente_id: str, venda_id: str) -> None:
        try:
            self._ddb.delete_item(
                TableName=self._vendas,
                Key=_serd({"pk": f"CLIENTE#{cliente_id}", "sk": "RESERVA_ATIVA"}),
                ConditionExpression="vendaId = :v",
                ExpressionAttributeValues=_serd({":v": venda_id}),
            )
        except self._ddb.exceptions.ConditionalCheckFailedException:
            return  # inexistente ou de outra venda = sucesso

    # -- tokens, desistencia e retirada
    # -------------------------------------------
    def _atualizar_condicional(
        self,
        venda_id: str,
        expressao: str,
        valores: dict[str, Any],
        condicao: str,
        nomes: dict[str, str] | None = None,
    ) -> bool:
        parametros: dict[str, Any] = {
            "TableName": self._vendas,
            "Key": _pk(venda_id),
            "UpdateExpression": expressao,
            "ConditionExpression": condicao,
            "ExpressionAttributeValues": _serd(valores),
        }
        if nomes:
            parametros["ExpressionAttributeNames"] = nomes
        try:
            self._ddb.update_item(**parametros)
        except self._ddb.exceptions.ConditionalCheckFailedException:
            return False
        return True

    def registrar_token(self, venda_id: str, etapa: str, token: str) -> bool:
        return self._atualizar_condicional(
            venda_id,
            "SET taskToken = :t, etapaEspera = :e",
            {":t": token, ":e": etapa, ":f": False},
            (
                "attribute_exists(pk) AND (attribute_not_exists(desistenciaSo"
                "licitada) OR desistenciaSolicitada = :f)"
            ),
        )

    def solicitar_desistencia(self, venda_id: str) -> bool:
        return self._atualizar_condicional(
            venda_id,
            "SET desistenciaSolicitada = :v",
            {":v": True, ":a": "RESERVADO", ":b": "AGUARDANDO_PAGAMENTO", ":c": "PAGO"},
            "attribute_not_exists(retiradaEm) AND #s IN (:a, :b, :c)",
            {"#s": "status"},
        )

    def registrar_retirada(
        self, venda_id: str, retirada_em: str, documentacao: DocumentacaoRetirada
    ) -> bool:
        return self._atualizar_condicional(
            venda_id,
            "SET retiradaEm = :r, documentacao = :d",
            {":r": retirada_em, ":d": documentacao, ":pago": "PAGO", ":f": False},
            "#s = :pago AND attribute_exists(taskToken) AND attribute_not_exists(retiradaEm) "
            "AND attribute_not_exists(retiradaEncerrada) "
            "AND (attribute_not_exists(desistenciaSolicitada) OR desistenciaSolicitada = :f)",
            {"#s": "status"},
        )

    def encerrar_retirada(self, venda_id: str) -> bool:
        # A mesma linha serializa o prazo e a retirada. Se a API venceu,
        # concluir a venda mesmo que o callback tenha se perdido.
        if self._atualizar_condicional(
            venda_id,
            "SET retiradaEncerrada = :v",
            {":v": True, ":p": "PAGO"},
            "#s = :p AND attribute_not_exists(retiradaEm)",
            {"#s": "status"},
        ):
            return False
        venda = self.obter(venda_id)
        if venda is None:
            raise EstadoInvalido("venda inexistente")
        if venda.retirada_em:
            return True
        raise EstadoInvalido("venda nao esta aguardando retirada")

    def definir_saga(self, venda_id: str, execution_arn: str) -> None:
        self._atualizar_condicional(
            venda_id, "SET sagaExecutionArn = :a", {":a": execution_arn}, "attribute_exists(pk)"
        )

    # -- listagens
    # -----------------------------------------------------------------
    def _pagina(  # noqa: PLR0913, PLR0917
        self,
        indice: str,
        pk_attr: str,
        sk_attr: str,
        pk: str,
        limite: int,
        cursor: Cursor | None,
    ) -> tuple[list[Venda], Cursor | None]:
        parametros: dict[str, Any] = {
            "TableName": self._vendas,
            "IndexName": indice,
            "KeyConditionExpression": f"{pk_attr} = :p",
            "ExpressionAttributeValues": _serd({":p": pk}),
            "ScanIndexForward": False,
            "Limit": limite + 1,
        }
        if cursor:
            parametros["ExclusiveStartKey"] = _serd(cursor)
        itens = [_des(i) for i in self._ddb.query(**parametros)["Items"]]
        proxima = None
        if len(itens) > limite:
            itens = itens[:limite]
            proxima = {k: itens[-1][k] for k in ("pk", "sk", pk_attr, sk_attr)}
        return [de_item(i) for i in itens], proxima

    def listar_por_status(
        self, status: StatusVenda, *, limite: int, cursor: Cursor | None
    ) -> tuple[list[Venda], Cursor | None]:
        return self._pagina(
            GSI_STATUS, "gsi2pk", "gsi2sk", f"STATUS#{status.value}", limite, cursor
        )

    def listar_do_cliente(
        self, cliente_id: str, *, limite: int, cursor: Cursor | None
    ) -> tuple[list[Venda], Cursor | None]:
        return self._pagina(
            GSI_CLIENTE, "gsi1pk", "gsi1sk", f"CLIENTE#{cliente_id}", limite, cursor
        )

    # -- varredura
    # ---------------------------------------------------------------
    def _por_status_antigo(
        self, status: StatusVenda, antes_de: str, filtro: str | None
    ) -> list[Venda]:
        parametros: dict[str, Any] = {
            "TableName": self._vendas,
            "IndexName": GSI_STATUS,
            "KeyConditionExpression": "gsi2pk = :p AND gsi2sk < :antes",
            "ExpressionAttributeValues": _serd(
                {":p": f"STATUS#{status.value}", ":antes": antes_de}
            ),
        }
        if filtro:
            parametros["FilterExpression"] = filtro
        return [de_item(_des(i)) for i in self._ddb.query(**parametros)["Items"]]

    def pendentes_de_saga(self, antes_de: str) -> list[Venda]:
        return self._por_status_antigo(
            StatusVenda.RESERVADO, antes_de, "attribute_not_exists(sagaExecutionArn)"
        )

    def criados_antigos(self, antes_de: str) -> list[Venda]:
        return self._por_status_antigo(StatusVenda.CRIADO, antes_de, None)
