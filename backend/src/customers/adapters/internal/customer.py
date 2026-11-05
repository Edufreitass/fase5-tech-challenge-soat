"""Cliente (Lambda Invoke) da fn-clientes-interno, usado por vendas e
pagamentos."""

import json
from typing import Any

from pydantic import TypeAdapter, ValidationError

from shared.contracts import DadosCobranca, DadosTitular, DocumentacaoCliente, ValidacaoComprador
from shared.errors import DependenciaIndisponivel


class InvocadorClientesInterno:
    def __init__(self, cliente_lambda: Any, nome_funcao: str) -> None:
        self._lambda = cliente_lambda
        self._nome = nome_funcao

    def _invocar(self, operacao: str, cliente_id: str) -> object:
        resposta = self._lambda.invoke(
            FunctionName=self._nome,
            Payload=json.dumps({"operacao": operacao, "clienteId": cliente_id}).encode(),
        )
        corpo: object = json.loads(resposta["Payload"].read())
        if resposta.get("FunctionError"):
            raise DependenciaIndisponivel("Servico de clientes indisponivel.")
        return corpo

    def _ler[T](self, operacao: str, cliente_id: str, contrato: type[T]) -> T:
        try:
            return TypeAdapter(contrato).validate_python(
                self._invocar(operacao, cliente_id), strict=True
            )
        except (ValidationError, json.JSONDecodeError):
            raise DependenciaIndisponivel("Resposta invalida do servico de clientes.") from None

    def validar_comprador(self, cliente_id: str) -> ValidacaoComprador:
        return self._ler("VALIDAR_COMPRADOR", cliente_id, ValidacaoComprador)

    def exportar_dados(self, cliente_id: str) -> DadosTitular:
        return self._ler("EXPORTAR_DADOS", cliente_id, DadosTitular)

    def obter_dados_documentacao(self, cliente_id: str) -> DocumentacaoCliente:
        return self._ler("OBTER_DADOS_DOCUMENTACAO", cliente_id, DocumentacaoCliente)

    def obter_dados_cobranca(self, cliente_id: str) -> DadosCobranca:
        return self._ler("OBTER_DADOS_COBRANCA", cliente_id, DadosCobranca)
