"""Adaptadores AWS (SSM e Cognito) das migracoes."""

from typing import Any


class SsmParametros:
    def __init__(self, cliente: Any, prefixo: str) -> None:
        self._ssm = cliente
        self._prefixo = prefixo

    def _caminho(self, nome: str) -> str:
        return f"{self._prefixo}/{nome}"

    def existe(self, nome: str) -> bool:
        return self.ler(nome) is not None

    def ler(self, nome: str) -> str | None:
        try:
            return str(
                self._ssm.get_parameter(Name=self._caminho(nome), WithDecryption=False)[
                    "Parameter"
                ]["Value"]
            )
        except self._ssm.exceptions.ParameterNotFound:
            return None

    def gravar(self, nome: str, valor: str, *, segredo: bool, sobrescrever: bool) -> bool:
        try:
            self._ssm.put_parameter(
                Name=self._caminho(nome),
                Value=valor,
                Type="SecureString" if segredo else "String",
                Overwrite=sobrescrever,
            )
        except self._ssm.exceptions.ParameterAlreadyExists:
            return False
        return True


class CognitoFuncionarios:
    def __init__(self, cliente: Any, pool_id: str) -> None:
        self._cognito = cliente
        self._pool = pool_id

    def garantir_funcionario(self, *, email: str, nome: str, grupo: str) -> None:
        try:
            usuario = self._cognito.admin_create_user(
                UserPoolId=self._pool,
                Username=email,
                UserAttributes=[
                    {"Name": "email", "Value": email},
                    {"Name": "email_verified", "Value": "true"},
                    {"Name": "name", "Value": nome},
                ],
                DesiredDeliveryMediums=["EMAIL"],
            )["User"]["Username"]
        except self._cognito.exceptions.UsernameExistsException:
            usuario = self._cognito.admin_get_user(UserPoolId=self._pool, Username=email)[
                "Username"
            ]
        self._cognito.admin_add_user_to_group(
            UserPoolId=self._pool, Username=usuario, GroupName=grupo
        )
