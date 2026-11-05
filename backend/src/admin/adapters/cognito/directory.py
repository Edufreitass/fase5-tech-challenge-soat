"""Adaptador Cognito (pool de funcionarios) para
`DiretorioFuncionarios`.
"""

from typing import Any

from botocore.exceptions import ClientError

from admin.domain.models import Funcionario, GrupoFuncionario, PaginaFuncionarios
from shared.errors import ConflitoUnicidade, RecursoNaoEncontrado


def _atributo(usuario: dict[str, Any], nome: str) -> str:
    atributos = usuario.get("UserAttributes") or usuario.get("Attributes") or []
    return next((a["Value"] for a in atributos if a["Name"] == nome), "")


class CognitoDiretorioFuncionarios:
    def __init__(self, cliente: Any, pool_id: str) -> None:
        self._cognito = cliente
        self._pool = pool_id

    def _montar(self, usuario: dict[str, Any]) -> Funcionario:
        username = usuario["Username"]
        grupos = self._cognito.admin_list_groups_for_user(UserPoolId=self._pool, Username=username)
        detalhe = self._cognito.admin_get_user(UserPoolId=self._pool, Username=username)
        return Funcionario(
            id=_atributo(usuario, "sub") or username,
            nome=_atributo(usuario, "name"),
            email=_atributo(usuario, "email"),
            grupos=tuple(sorted(g["GroupName"] for g in grupos["Groups"])),
            ativo=bool(usuario.get("Enabled", True)),
            mfa_configurado=bool(detalhe.get("UserMFASettingList")),
        )

    def listar(
        self, *, grupo: GrupoFuncionario | None, limite: int, proximo: str | None
    ) -> PaginaFuncionarios:
        parametros: dict[str, Any] = {"UserPoolId": self._pool, "Limit": limite}
        if proximo:
            parametros["NextToken" if grupo else "PaginationToken"] = proximo
        if grupo:
            resposta = self._cognito.list_users_in_group(GroupName=grupo.value, **parametros)
            token = resposta.get("NextToken")
        else:
            resposta = self._cognito.list_users(**parametros)
            token = resposta.get("PaginationToken")
        return PaginaFuncionarios([self._montar(u) for u in resposta["Users"]], token)

    def obter(self, funcionario_id: str) -> Funcionario:
        try:
            usuario = self._cognito.admin_get_user(UserPoolId=self._pool, Username=funcionario_id)
        except self._cognito.exceptions.UserNotFoundException as erro:
            raise RecursoNaoEncontrado("Funcionario nao encontrado.") from erro
        return self._montar(usuario)

    def criar(self, *, nome: str, email: str, grupo: GrupoFuncionario) -> Funcionario:
        try:
            criado = self._cognito.admin_create_user(
                UserPoolId=self._pool,
                Username=email,
                UserAttributes=[
                    {"Name": "email", "Value": email},
                    {"Name": "email_verified", "Value": "true"},
                    {"Name": "name", "Value": nome},
                ],
                DesiredDeliveryMediums=["EMAIL"],
            )["User"]
        except self._cognito.exceptions.UsernameExistsException as erro:
            raise ConflitoUnicidade("Ja existe funcionario com este e-mail.") from erro
        self._cognito.admin_add_user_to_group(
            UserPoolId=self._pool, Username=criado["Username"], GroupName=grupo.value
        )
        return self._montar(criado)

    def trocar_grupo(self, funcionario_id: str, grupo: GrupoFuncionario) -> None:
        atuais = self._cognito.admin_list_groups_for_user(
            UserPoolId=self._pool, Username=funcionario_id
        )["Groups"]
        for existente in atuais:
            if existente["GroupName"] != grupo.value:
                self._cognito.admin_remove_user_from_group(
                    UserPoolId=self._pool,
                    Username=funcionario_id,
                    GroupName=existente["GroupName"],
                )
        if all(g["GroupName"] != grupo.value for g in atuais):
            self._cognito.admin_add_user_to_group(
                UserPoolId=self._pool, Username=funcionario_id, GroupName=grupo.value
            )

    def definir_ativo(self, funcionario_id: str, *, ativo: bool) -> None:
        try:
            if ativo:
                self._cognito.admin_enable_user(UserPoolId=self._pool, Username=funcionario_id)
            else:
                self._cognito.admin_disable_user(UserPoolId=self._pool, Username=funcionario_id)
                self._cognito.admin_user_global_sign_out(
                    UserPoolId=self._pool, Username=funcionario_id
                )
        except ClientError as erro:
            if erro.response["Error"]["Code"] == "UserNotFoundException":
                raise RecursoNaoEncontrado("Funcionario nao encontrado.") from erro
            raise
