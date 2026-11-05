"""Envio de callbacks ao Step Functions (SendTaskSuccess/Failure)
tolerante
a token consumido.
"""

import json
from typing import Any

from shared.contracts import EntradaSaga


class CallbackStepFunctions:
    def __init__(self, cliente: Any) -> None:
        self._sfn = cliente

    def _tolerante(self, chamada: Any, **kwargs: Any) -> bool:
        excecoes = self._sfn.exceptions
        try:
            chamada(**kwargs)
        except (excecoes.TaskTimedOut, excecoes.InvalidToken, excecoes.TaskDoesNotExist):
            return False
        return True

    def enviar_sucesso(self, token: str, saida: dict[str, Any]) -> bool:
        return self._tolerante(
            self._sfn.send_task_success, taskToken=token, output=json.dumps(saida)
        )

    def enviar_falha(self, token: str, erro: str, causa: str) -> bool:
        return self._tolerante(
            self._sfn.send_task_failure, taskToken=token, error=erro, cause=causa
        )


class SagaStepFunctions(CallbackStepFunctions):
    """Inicio idempotente da execucao (nome = vendaId) alem dos
    callbacks.
    """

    def __init__(self, cliente: Any, state_machine_arn: str) -> None:
        super().__init__(cliente)
        self._arn = state_machine_arn

    def iniciar(self, entrada: EntradaSaga, nome: str) -> str:
        try:
            return str(
                self._sfn.start_execution(
                    stateMachineArn=self._arn, name=nome, input=json.dumps(entrada)
                )["executionArn"]
            )
        except self._sfn.exceptions.ExecutionAlreadyExists:
            # ExecutionAlreadyExists = sucesso (StartExecution
            # idempotente)
            return f"{self._arn.replace(':stateMachine:', ':execution:')}:{nome}"
