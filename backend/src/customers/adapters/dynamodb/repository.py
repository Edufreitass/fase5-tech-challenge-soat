"""Repositorio DynamoDB de clientes (tabela isolada `clientes`)."""

from collections.abc import Iterator
from datetime import date
from typing import Any

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

from customers.domain.models import (
    Cliente,
    Consentimento,
    ConsentimentoVigente,
    Endereco,
    RetencaoLegal,
    RgArmazenado,
    SolicitacaoLgpd,
    StatusCliente,
)
from customers.domain.rules import campos_pendentes
from shared.dynamo import transacionar
from shared.errors import ConflitoUnicidade, VersaoDesatualizada

_SER = TypeSerializer()
_DES = TypeDeserializer()


def _ser(item: dict[str, Any]) -> dict[str, Any]:
    return {k: _SER.serialize(v) for k, v in item.items() if v is not None}


def _des(item: dict[str, Any]) -> dict[str, Any]:
    return {k: _DES.deserialize(v) for k, v in item.items()}


def para_item(c: Cliente) -> dict[str, Any]:
    e = c.endereco
    item: dict[str, Any] = {
        "pk": f"CLIENTE#{c.id}",
        "sk": "PERFIL",
        "tipo": "CLIENTE",
        "id": c.id,
        "nomeCompleto": c.nome_completo,
        "cpfCifrado": c.cpf_cifrado,
        "cpfHmac": c.cpf_hmac,
        "cpfFinal": c.cpf_final,
        "dataNascimento": c.data_nascimento.isoformat(),
        "email": c.email,
        "emailVerificado": c.email_verificado,
        "telefone": c.telefone,
        "endereco": {
            "cep": e.cep,
            "logradouro": e.logradouro,
            "numero": e.numero,
            "complemento": e.complemento,
            "bairro": e.bairro,
            "cidade": e.cidade,
            "uf": e.uf,
        },
        "consentimentoVigente": {
            "versaoTermo": c.consentimento_vigente.versao_termo,
            "aceitoEm": c.consentimento_vigente.aceito_em,
        },
        "cadastroCompleto": c.cadastro_completo,
        "status": c.status.value,
        "ultimaAtividadeEm": c.ultima_atividade_em,
        "criadoEm": c.criado_em,
        "atualizadoEm": c.atualizado_em,
        "versao": c.versao,
    }
    if c.rg:
        item["rg"] = {
            "numeroCifrado": c.rg.numero_cifrado,
            "numeroFinal": c.rg.numero_final,
            "numeroMascarado": c.rg.numero_mascarado,
            "orgaoEmissor": c.rg.orgao_emissor,
            "uf": c.rg.uf,
        }
    if c.cnh_cifrada:
        item["cnhCifrada"] = c.cnh_cifrada
        item["cnhFinal"] = c.cnh_final
    item["endereco"] = {k: v for k, v in item["endereco"].items() if v is not None}
    return item


def de_item(i: dict[str, Any]) -> Cliente:
    e = i["endereco"]
    rg = None
    if "rg" in i:
        r = i["rg"]
        rg = RgArmazenado(
            r["numeroCifrado"], r["numeroFinal"], r["numeroMascarado"], r["orgaoEmissor"], r["uf"]
        )
    consentimento = ConsentimentoVigente(
        i["consentimentoVigente"]["versaoTermo"], i["consentimentoVigente"]["aceitoEm"]
    )
    return Cliente(
        id=i["id"],
        nome_completo=i["nomeCompleto"],
        cpf_cifrado=i["cpfCifrado"],
        cpf_hmac=i["cpfHmac"],
        cpf_final=i["cpfFinal"],
        data_nascimento=date.fromisoformat(i["dataNascimento"]),
        email=i["email"],
        email_verificado=bool(i["emailVerificado"]),
        telefone=i["telefone"],
        endereco=Endereco(
            cep=e["cep"],
            logradouro=e["logradouro"],
            numero=e["numero"],
            bairro=e["bairro"],
            cidade=e["cidade"],
            uf=e["uf"],
            complemento=e.get("complemento"),
        ),
        consentimento_vigente=consentimento,
        status=StatusCliente(i["status"]),
        criado_em=i["criadoEm"],
        atualizado_em=i["atualizadoEm"],
        ultima_atividade_em=i["ultimaAtividadeEm"],
        versao=int(i["versao"]),
        rg=rg,
        cnh_cifrada=i.get("cnhCifrada"),
        cnh_final=i.get("cnhFinal"),
        campos_pendentes=campos_pendentes(
            rg=rg, email_verificado=bool(i["emailVerificado"]), consentimento_vigente=True
        ),
    )


class DynamoDBClienteRepository:
    def __init__(self, cliente: Any, tabela: str) -> None:
        self._ddb = cliente
        self._tabela = tabela

    def _put(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "Put": {
                "TableName": self._tabela,
                "Item": _ser(item),
                "ConditionExpression": "attribute_not_exists(pk) AND attribute_not_exists(sk)",
            }
        }

    def criar(self, cliente: Cliente, consentimento: Consentimento, *, email_hmac: str) -> None:
        pk = f"CLIENTE#{cliente.id}"
        itens = [
            self._put(para_item(cliente)),
            self._put({"pk": f"CPF#{cliente.cpf_hmac}", "sk": "UNIQ", "clienteId": cliente.id}),
            self._put({"pk": f"EMAIL#{email_hmac}", "sk": "UNIQ", "clienteId": cliente.id}),
            self._put(
                {
                    "pk": pk,
                    "sk": f"CONSENTIMENTO#{consentimento.versao_termo}#{consentimento.aceito_em}",
                    "tipo": "CONSENTIMENTO",
                    "versaoTermo": consentimento.versao_termo,
                    "finalidades": [f.value for f in consentimento.finalidades],
                    "aceito": consentimento.aceito,
                    "aceitoEm": consentimento.aceito_em,
                    "ipHmac": consentimento.ip_hmac,
                    "userAgent": consentimento.user_agent,
                }
            ),
        ]
        try:
            transacionar(self._ddb, itens)
        except self._ddb.exceptions.TransactionCanceledException as erro:
            raise ConflitoUnicidade("CPF, e-mail ou cadastro ja existente.") from erro

    def obter(self, cliente_id: str) -> Cliente | None:
        resposta = self._ddb.get_item(
            TableName=self._tabela,
            Key=_ser({"pk": f"CLIENTE#{cliente_id}", "sk": "PERFIL"}),
            ConsistentRead=True,
        )
        if "Item" not in resposta:
            return None
        item = _des(resposta["Item"])
        # perfil anonimizado nao e mais um cliente: some das consultas
        # (o historico fica na trilha)
        return None if item["status"] == StatusCliente.ANONIMIZADO.value else de_item(item)

    def atualizar(self, cliente: Cliente, versao_esperada: int) -> None:
        try:
            self._ddb.put_item(
                TableName=self._tabela,
                Item=_ser(para_item(cliente)),
                ConditionExpression="versao = :v",
                ExpressionAttributeValues=_ser({":v": versao_esperada}),
            )
        except self._ddb.exceptions.ConditionalCheckFailedException as erro:
            raise VersaoDesatualizada("O perfil foi alterado; releia e tente de novo.") from erro

    def registrar_consentimento(
        self,
        cliente_id: str,
        consentimento: Consentimento,
        vigente: ConsentimentoVigente | None,
        agora: str,
    ) -> None:
        itens: list[dict[str, Any]] = [
            self._put(
                {
                    "pk": f"CLIENTE#{cliente_id}",
                    "sk": f"CONSENTIMENTO#{consentimento.versao_termo}#{consentimento.aceito_em}",
                    "tipo": "CONSENTIMENTO",
                    "versaoTermo": consentimento.versao_termo,
                    "finalidades": [f.value for f in consentimento.finalidades],
                    "aceito": consentimento.aceito,
                    "aceitoEm": consentimento.aceito_em,
                    "ipHmac": consentimento.ip_hmac,
                    "userAgent": consentimento.user_agent,
                }
            )
        ]
        if vigente is not None:
            itens.append(
                {
                    "Update": {
                        "TableName": self._tabela,
                        "Key": _ser({"pk": f"CLIENTE#{cliente_id}", "sk": "PERFIL"}),
                        "UpdateExpression": (
                            "SET consentimentoVigente = :c, atualizadoEm = :t, versao = v"
                            "ersao + :um"
                        ),
                        "ConditionExpression": "attribute_exists(pk)",
                        "ExpressionAttributeValues": _ser(
                            {
                                ":c": {
                                    "versaoTermo": vigente.versao_termo,
                                    "aceitoEm": vigente.aceito_em,
                                },
                                ":t": agora,
                                ":um": 1,
                            }
                        ),
                    }
                }
            )
        transacionar(self._ddb, itens)

    # -- LGPD: exportacao, exclusao, retencao
    # ------------------------------------------
    def status_do_perfil(self, cliente_id: str) -> str | None:
        r = self._ddb.get_item(
            TableName=self._tabela,
            Key=_ser({"pk": f"CLIENTE#{cliente_id}", "sk": "PERFIL"}),
            ConsistentRead=True,
            ProjectionExpression="#s",
            ExpressionAttributeNames={"#s": "status"},
        )
        return str(_des(r["Item"])["status"]) if "Item" in r else None

    def consentimentos(self, cliente_id: str) -> list[dict[str, Any]]:
        r = self._ddb.query(
            TableName=self._tabela,
            ConsistentRead=True,
            KeyConditionExpression="pk = :p AND begins_with(sk, :c)",
            ExpressionAttributeValues=_ser(
                {":p": f"CLIENTE#{cliente_id}", ":c": "CONSENTIMENTO#"}
            ),
        )
        return [
            {k: i[k] for k in ("versaoTermo", "finalidades", "aceito", "aceitoEm") if k in i}
            for i in (_des(x) for x in r["Items"])
        ]

    def ultima_exportacao(self, cliente_id: str) -> str | None:
        r = self._ddb.query(
            TableName=self._tabela,
            ConsistentRead=True,
            ScanIndexForward=False,
            KeyConditionExpression="pk = :p AND begins_with(sk, :l)",
            FilterExpression="operacao = :o AND #s = :c",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues=_ser(
                {
                    ":p": f"CLIENTE#{cliente_id}",
                    ":l": "LGPD#",
                    ":o": "EXPORTACAO",
                    ":c": "CONCLUIDA",
                }
            ),
        )
        itens = [_des(x) for x in r["Items"]]
        return str(max(i["criadoEm"] for i in itens)) if itens else None

    @staticmethod
    def _item_solicitacao(s: SolicitacaoLgpd) -> dict[str, Any]:
        return {
            "pk": f"CLIENTE#{s.cliente_id}",
            "sk": f"LGPD#{s.id}",
            "tipo": "SOLICITACAO_LGPD",
            "id": s.id,
            "clienteId": s.cliente_id,
            "operacao": s.operacao,
            "status": s.status,
            "motivoRejeicao": s.motivo_rejeicao,
            "criadoEm": s.criado_em,
        }

    def registrar_solicitacao(self, solicitacao: SolicitacaoLgpd) -> None:
        self._ddb.put_item(TableName=self._tabela, Item=_ser(self._item_solicitacao(solicitacao)))

    def anonimizar(
        self,
        cliente: Cliente,
        *,
        email_hmac: str,
        retencao: RetencaoLegal | None,
        solicitacao: SolicitacaoLgpd,
        agora: str,
    ) -> None:
        anonimo = {
            "pk": f"CLIENTE#{cliente.id}",
            "sk": "PERFIL",
            "tipo": "CLIENTE",
            "id": cliente.id,
            "nomeCompleto": "ANONIMIZADO",
            "status": StatusCliente.ANONIMIZADO.value,
            "criadoEm": cliente.criado_em,
            "atualizadoEm": agora,
            "ultimaAtividadeEm": agora,
            "versao": cliente.versao + 1,
        }
        itens: list[dict[str, Any]] = [
            {
                "Put": {
                    "TableName": self._tabela,
                    "Item": _ser(anonimo),
                    "ConditionExpression": "versao = :v",
                    "ExpressionAttributeValues": _ser({":v": cliente.versao}),
                }
            },
            {
                "Delete": {
                    "TableName": self._tabela,
                    "Key": _ser({"pk": f"CPF#{cliente.cpf_hmac}", "sk": "UNIQ"}),
                }
            },
            {
                "Delete": {
                    "TableName": self._tabela,
                    "Key": _ser({"pk": f"EMAIL#{email_hmac}", "sk": "UNIQ"}),
                }
            },
            {
                "Put": {
                    "TableName": self._tabela,
                    "Item": _ser(self._item_solicitacao(solicitacao)),
                }
            },
        ]
        if retencao is not None:
            itens.append(
                {
                    "Put": {
                        "TableName": self._tabela,
                        "Item": _ser(
                            {
                                "pk": f"CLIENTE#{cliente.id}",
                                "sk": "RETENCAO_LEGAL",
                                "tipo": "RETENCAO_LEGAL",
                                "nomeCompleto": retencao.nome_completo,
                                "cpfCifrado": retencao.cpf_cifrado,
                                "vendas": list(retencao.vendas),
                                "expiraEm": retencao.expira_em,
                            }
                        ),
                    }
                }
            )
        try:
            transacionar(self._ddb, itens)
        except self._ddb.exceptions.TransactionCanceledException as erro:
            raise VersaoDesatualizada(
                "O perfil foi alterado durante a exclusao; tente de novo."
            ) from erro

    def inativos_desde(self, limite_iso: str) -> Iterator[Cliente]:
        inicio: dict[str, Any] | None = None
        while True:
            parametros: dict[str, Any] = {
                "TableName": self._tabela,
                "Limit": 50,
                "ConsistentRead": True,
                "FilterExpression": "sk = :perfil AND #s = :ativo AND ultimaAtividadeEm < :limite",
                "ExpressionAttributeNames": {"#s": "status"},
                "ExpressionAttributeValues": _ser(
                    {":perfil": "PERFIL", ":ativo": "ATIVO", ":limite": limite_iso}
                ),
            }
            if inicio:
                parametros["ExclusiveStartKey"] = inicio
            resposta = self._ddb.scan(**parametros)
            for item in resposta["Items"]:
                yield de_item(_des(item))
            inicio = resposta.get("LastEvaluatedKey")
            if not inicio:
                return

    def todos_os_perfis(self) -> list[Cliente]:
        perfis: list[Cliente] = []
        inicio: dict[str, Any] | None = None
        while True:
            parametros: dict[str, Any] = {
                "TableName": self._tabela,
                "Limit": 50,
                "ConsistentRead": True,
                "FilterExpression": "sk = :perfil AND #s = :ativo",
                "ExpressionAttributeNames": {"#s": "status"},
                "ExpressionAttributeValues": _ser({":perfil": "PERFIL", ":ativo": "ATIVO"}),
            }
            if inicio:
                parametros["ExclusiveStartKey"] = inicio
            resposta = self._ddb.scan(**parametros)
            perfis += [de_item(_des(i)) for i in resposta["Items"]]
            inicio = resposta.get("LastEvaluatedKey")
            if not inicio:
                return perfis

    def retencoes_legais(self) -> list[tuple[str, str]]:
        itens: list[tuple[str, str]] = []
        inicio: dict[str, Any] | None = None
        while True:
            parametros: dict[str, Any] = {
                "TableName": self._tabela,
                "ConsistentRead": True,
                "FilterExpression": "sk = :r",
                "ExpressionAttributeValues": _ser({":r": "RETENCAO_LEGAL"}),
            }
            if inicio:
                parametros["ExclusiveStartKey"] = inicio
            resposta = self._ddb.scan(**parametros)
            for bruto in resposta["Items"]:
                i = _des(bruto)
                itens.append((i["pk"].removeprefix("CLIENTE#"), i["cpfCifrado"]))
            inicio = resposta.get("LastEvaluatedKey")
            if not inicio:
                return itens

    def atualizar_cpf_retencao(self, cliente_id: str, cpf_cifrado: str) -> None:
        self._ddb.update_item(
            TableName=self._tabela,
            Key=_ser({"pk": f"CLIENTE#{cliente_id}", "sk": "RETENCAO_LEGAL"}),
            UpdateExpression="SET cpfCifrado = :c",
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeValues=_ser({":c": cpf_cifrado}),
        )
