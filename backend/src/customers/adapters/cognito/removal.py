from typing import Any


class CognitoRemocao:
    """Remove o usuario do pool de clientes (exclusao LGPD)."""

    def __init__(self, cliente: Any, pool_id: str) -> None:
        self._cognito = cliente
        self._pool = pool_id

    def remover(self, cliente_id: str) -> None:
        try:
            self._cognito.admin_delete_user(UserPoolId=self._pool, Username=cliente_id)
        except self._cognito.exceptions.UserNotFoundException:
            return
