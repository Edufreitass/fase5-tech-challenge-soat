"""Fixtures do E2E contra o ambiente `dev` (rodam so no workflow
e2e.yml,
com credenciais AWS).
"""

import json
import os
import random
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import boto3
import httpx
import pytest

PREFIXO = "revenda-dev-"
SENHA = "Teste!Carga-123456"  # usuarios de teste descartaveis, apagados ao final
REGIAO = "us-east-1"


@dataclass
class Ambiente:
    api_url: str
    pool_clientes: str
    client_id: str
    versao_termo: str
    sessao: boto3.Session
    cpfs: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    usuarios: list[str] = field(default_factory=list)


def cpf_valido(base9: str) -> str:
    d = [int(c) for c in base9]
    for n in (9, 10):
        d.append(
            sum(x * p for x, p in zip(d[:n], range(n + 1, 1, -1), strict=True)) * 10 % 11 % 10
        )
    return "".join(map(str, d))


@pytest.fixture(scope="session")
def ambiente() -> Iterator[Ambiente]:
    sessao = boto3.Session(region_name=REGIAO)
    cfg = sessao.client("lambda").get_function_configuration(
        FunctionName=PREFIXO + "fn-clientes-api"
    )["Environment"]["Variables"]
    api_id = next(
        a["id"]
        for a in sessao.client("apigateway").get_rest_apis(limit=50)["items"]
        if a["name"] == PREFIXO + "api"
    )
    versao = sessao.client("ssm").get_parameter(Name="/revenda/dev/params/versao-termo-vigente")[
        "Parameter"
    ]["Value"]
    amb = Ambiente(
        f"https://{api_id}.execute-api.{REGIAO}.amazonaws.com/v1",
        cfg["POOL_CLIENTES_ID"],
        cfg["CLIENT_ID_CLIENTES"],
        versao,
        sessao,
    )
    yield amb
    cognito = sessao.client("cognito-idp")
    for username in amb.usuarios:
        try:
            cognito.admin_delete_user(UserPoolId=amb.pool_clientes, Username=username)
        except cognito.exceptions.UserNotFoundException:
            continue


def criar_comprador(amb: Ambiente, indice: int) -> dict[str, str]:
    """Cria usuario no Cognito (senha permanente), obtem o access token
    (auth admin) e cadastra o perfil."""
    cognito = amb.sessao.client("cognito-idp")
    email = f"e2e{indice}-{uuid.uuid4().hex[:8]}@example.com"
    cognito.admin_create_user(
        UserPoolId=amb.pool_clientes,
        Username=email,
        MessageAction="SUPPRESS",
        UserAttributes=[
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "true"},
        ],
    )
    cognito.admin_set_user_password(
        UserPoolId=amb.pool_clientes, Username=email, Password=SENHA, Permanent=True
    )
    token = cognito.admin_initiate_auth(
        UserPoolId=amb.pool_clientes,
        ClientId=amb.client_id,
        AuthFlow="ADMIN_USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email, "PASSWORD": SENHA},
    )["AuthenticationResult"]["AccessToken"]
    cpf = cpf_valido(f"{random.randint(100000000, 999999999):09d}")  # noqa: S311
    corpo: dict[str, Any] = {
        "nomeCompleto": "Cliente Carga E2E",
        "cpf": cpf,
        "dataNascimento": "1990-05-12",
        "telefone": "+5511987654321",
        "endereco": {
            "cep": "01310100",
            "logradouro": "Av Paulista",
            "numero": "1",
            "bairro": "Bela Vista",
            "cidade": "Sao Paulo",
            "uf": "SP",
        },
        "rg": {"numero": "12.345.678-9", "orgaoEmissor": "SSP", "uf": "SP"},
        "consentimento": {
            "versaoTermo": amb.versao_termo,
            "aceito": True,
            "finalidades": ["EXECUCAO_CONTRATO"],
        },
    }
    resposta = httpx.post(
        f"{amb.api_url}/clientes",
        json=corpo,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    assert resposta.status_code == 201, resposta.text
    amb.usuarios.append(email)
    amb.cpfs.append(cpf)
    amb.emails.append(email)
    return {"email": email, "cpf": cpf, "token": token}


@pytest.fixture(scope="session")
def compradores(ambiente: Ambiente) -> list[dict[str, str]]:
    return [criar_comprador(ambiente, i) for i in range(10)]


def salvar(nome: str, dados: Any) -> None:
    os.makedirs("build/evidencias", exist_ok=True)
    with open(f"build/evidencias/{nome}", "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2, default=str)
