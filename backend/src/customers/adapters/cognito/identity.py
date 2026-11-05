from typing import Any


class CognitoIdentidade:
    """Le o e-mail verificado no pool de clientes (o access token nao
    traz
    o claim `email`).
    """

    def __init__(self, cliente: Any, pool_id: str) -> None:
        self._cognito = cliente
        self._pool = pool_id

    def obter_email(self, cliente_id: str) -> tuple[str, bool]:
        usuario = self._cognito.admin_get_user(UserPoolId=self._pool, Username=cliente_id)
        atributos = {a["Name"]: a["Value"] for a in usuario["UserAttributes"]}
        return atributos.get("email", ""), atributos.get("email_verified") == "true"
