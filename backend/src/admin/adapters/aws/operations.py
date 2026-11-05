"""Adaptadores AWS das operacoes administrativas."""

import json
import secrets
from datetime import datetime
from typing import Any

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

from admin.domain.operations import FiltroAuditoria
from shared import crypto as cripto
from shared.contracts import Cursor

_SER = TypeSerializer()
_DES = TypeDeserializer()


def _ms(momento: datetime) -> int:
    return int(momento.timestamp() * 1000)


class AuditoriaCloudWatch:
    """FilterLogEvents no log group de auditoria, com filter pattern
    montado de allowlist."""

    def __init__(self, cliente: Any, grupo: str) -> None:
        self._logs = cliente
        self._grupo = grupo

    @staticmethod
    def padrao(f: FiltroAuditoria) -> str:
        condicoes = []
        if f.cliente_id:
            condicoes.append(f'($.clienteId = "{f.cliente_id}" || $.recurso = "{f.cliente_id}")')
        if f.ator_id:
            condicoes.append(f'$.atorId = "{f.ator_id}"')
        if f.acao:
            condicoes.append(f'($.tipo = "{f.acao}" || $.acao = "{f.acao}")')
        return "{ " + " && ".join(condicoes) + " }" if condicoes else ""

    def buscar(
        self, filtro: FiltroAuditoria, *, limite: int, proximo: str | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        parametros: dict[str, Any] = {
            "logGroupName": self._grupo,
            "startTime": _ms(filtro.de),
            "endTime": _ms(filtro.ate),
            "limit": limite,
        }
        if padrao := self.padrao(filtro):
            parametros["filterPattern"] = padrao
        if proximo:
            parametros["nextToken"] = proximo
        resposta = self._logs.filter_log_events(**parametros)
        itens = [json.loads(e["message"]) for e in resposta.get("events", [])]
        return itens, resposta.get("nextToken")


class SagasStepFunctions:
    def __init__(self, cliente: Any, state_machine_arn: str) -> None:
        self._sfn = cliente
        self._arn = state_machine_arn

    def _execucao(self, venda_id: str) -> str:
        return f"{self._arn.replace(':stateMachine:', ':execution:')}:{venda_id}"

    def listar(
        self, status: str, *, limite: int, proximo: str | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        parametros: dict[str, Any] = {
            "stateMachineArn": self._arn,
            "statusFilter": status,
            "maxResults": limite,
        }
        if proximo:
            parametros["nextToken"] = proximo
        r = self._sfn.list_executions(**parametros)
        itens = [
            {
                "vendaId": e["name"],
                "executionArn": e["executionArn"],
                "status": e["status"],
                "inicio": e["startDate"].isoformat(),
                "fim": e["stopDate"].isoformat() if e.get("stopDate") else None,
            }
            for e in r["executions"]
        ]
        return itens, r.get("nextToken")

    def status_da_execucao(self, venda_id: str) -> str | None:
        try:
            return str(
                self._sfn.describe_execution(executionArn=self._execucao(venda_id))["status"]
            )
        except self._sfn.exceptions.ExecutionDoesNotExist:
            return None

    def reprocessar(self, venda_id: str) -> None:
        self._sfn.redrive_execution(executionArn=self._execucao(venda_id))


class SolicitacoesDynamo:
    """`Scan` paginado (operacao administrativa de baixo volume)."""

    def __init__(self, cliente: Any, tabela: str) -> None:
        self._ddb = cliente
        self._tabela = tabela

    def listar(
        self, *, limite: int, cursor: Cursor | None
    ) -> tuple[list[dict[str, Any]], Cursor | None]:
        parametros: dict[str, Any] = {
            "TableName": self._tabela,
            "Limit": 50,
            "ConsistentRead": True,
            "FilterExpression": "tipo = :t",
            "ExpressionAttributeValues": {":t": _SER.serialize("SOLICITACAO_LGPD")},
        }
        itens: list[dict[str, Any]] = []
        inicio = {k: _SER.serialize(v) for k, v in cursor.items()} if cursor else None
        proxima: dict[str, Any] | None = None
        while len(itens) < limite:
            if inicio:
                parametros["ExclusiveStartKey"] = inicio
            r = self._ddb.scan(**parametros)
            for bruto in r["Items"]:
                i = {k: _DES.deserialize(v) for k, v in bruto.items()}
                itens.append(
                    {
                        k: i.get(k)
                        for k in (
                            "id",
                            "clienteId",
                            "operacao",
                            "status",
                            "motivoRejeicao",
                            "criadoEm",
                        )
                    }
                )
            inicio = r.get("LastEvaluatedKey")
            proxima = {k: _DES.deserialize(v) for k, v in inicio.items()} if inicio else None
            if not inicio:
                break
        return itens[:limite], proxima if len(itens) <= limite else None


class SegredosSsm:
    def __init__(self, ssm: Any, lambda_cliente: Any, prefixo: str, funcao_lgpd: str) -> None:
        self._ssm = ssm
        self._lambda = lambda_cliente
        self._prefixo = prefixo
        self._funcao = funcao_lgpd

    def rotacionar_webhook(self) -> int:
        resposta = self._ssm.put_parameter(
            Name=f"{self._prefixo}/segredos/webhook-hmac-atual",
            Value=secrets.token_urlsafe(32),
            Type="SecureString",
            Overwrite=True,
        )
        return int(resposta["Version"])

    def rotacionar_chave_pii(self) -> int:
        atual = int(
            self._ssm.get_parameter(Name=f"{self._prefixo}/pii/versao-atual")["Parameter"]["Value"]
        )
        nova = atual + 1
        privada, publica = cripto.gerar_par_chaves()
        self._ssm.put_parameter(
            Name=f"{self._prefixo}/segredos/pii-chave-privada-v{nova}",
            Value=privada,
            Type="SecureString",
        )
        self._ssm.put_parameter(
            Name=f"{self._prefixo}/pii/chave-publica-v{nova}", Value=publica, Type="String"
        )
        self._ssm.put_parameter(
            Name=f"{self._prefixo}/pii/versao-atual",
            Value=str(nova),
            Type="String",
            Overwrite=True,
        )
        self._lambda.invoke(
            FunctionName=self._funcao,
            InvocationType="Event",
            Payload=json.dumps(
                {"acao": "RECIFRAR", "versaoNova": nova, "versoesAntigas": list(range(1, nova))}
            ).encode(),
        )
        return nova
