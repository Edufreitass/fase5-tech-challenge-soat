"""POST/GET /clientes com DynamoDB, SSM e Cognito simulados (moto)."""

import json
import logging
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from aws_lambda_powertools.utilities import parameters
from moto import mock_aws

from customers.adapters.api import handler as modulo
from customers.adapters.cognito.identity import CognitoIdentidade
from customers.adapters.crypto.fields import DecifradorSealedBox
from customers.adapters.dynamodb.repository import DynamoDBClienteRepository
from customers.adapters.internal import handler as interno
from shared import crypto as cripto
from shared import parameters as parametros

CPF = "529.982.247-25"
CORPO: dict[str, Any] = {
    "nomeCompleto": "Maria Souza Lima",
    "cpf": CPF,
    "dataNascimento": "1990-05-12",
    "telefone": "+5511987654321",
    "endereco": {
        "cep": "01310-100",
        "logradouro": "Av. Paulista",
        "numero": "1000",
        "complemento": "Ap 101",
        "bairro": "Bela Vista",
        "cidade": "Sao Paulo",
        "uf": "SP",
    },
    "rg": {"numero": "12.345.678-9", "orgaoEmissor": "SSP", "uf": "SP"},
    "consentimento": {
        "versaoTermo": "2026-10-v1",
        "aceito": True,
        "finalidades": ["EXECUCAO_CONTRATO"],
    },
}


class Ambiente:
    def __init__(self) -> None:
        self.ddb = boto3.client("dynamodb")
        self.cognito = boto3.client("cognito-idp")
        self.pool = self.cognito.create_user_pool(PoolName="cli", UsernameAttributes=["email"])[
            "UserPool"
        ]["Id"]
        self.privada, publica = cripto.gerar_par_chaves()
        ssm = boto3.client("ssm")
        for nome, valor, tipo in (
            ("pii/versao-atual", "1", "String"),
            ("pii/chave-publica-v1", publica, "String"),
            ("segredos/pii-chave-privada-v1", self.privada, "SecureString"),
            ("segredos/cpf-hmac", "segredo-hmac", "SecureString"),
            ("params/versao-termo-vigente", "2026-10-v1", "String"),
        ):
            ssm.put_parameter(Name=f"/revenda/dev/{nome}", Value=valor, Type=tipo)
        self.ddb.create_table(
            TableName="t-clientes",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": a, "AttributeType": "S"} for a in ("pk", "sk")
            ],
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
        )

    def usuario(self, email: str, verificado: bool = True) -> dict[str, str]:
        criado = self.cognito.admin_create_user(
            UserPoolId=self.pool,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": str(verificado).lower()},
            ],
        )["User"]
        sub = next(a["Value"] for a in criado["Attributes"] if a["Name"] == "sub")
        return {
            "sub": sub,
            "token_use": "access",
            "client_id": "cid-cli",
            "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_CLI",
        }


@pytest.fixture
def amb(monkeypatch: pytest.MonkeyPatch) -> Iterator[Ambiente]:
    with mock_aws():
        a = Ambiente()
        repo = DynamoDBClienteRepository(a.ddb, "t-clientes")
        monkeypatch.setattr(modulo, "_repositorio", lambda: repo)
        monkeypatch.setattr(modulo, "_identidade", lambda: CognitoIdentidade(a.cognito, a.pool))
        monkeypatch.setattr(interno, "_repositorio", lambda: repo)
        parameters.base.DEFAULT_PROVIDERS.clear()  # type: ignore[attr-defined]
        parametros.segredo_cursor.cache_clear()
        yield a


def chamar(
    metodo: str, caminho: str, claims: dict[str, str] | None = None, corpo: Any = None
) -> tuple[int, Any, dict[str, str]]:
    evento = {
        "httpMethod": metodo,
        "path": caminho,
        "resource": caminho,
        "headers": {"User-Agent": "pytest"},
        "multiValueHeaders": {},
        "queryStringParameters": None,
        "body": json.dumps(corpo) if corpo is not None else None,
        "isBase64Encoded": False,
        "requestContext": {
            "authorizer": {"claims": claims} if claims else None,
            "requestId": "r",
            "stage": "v1",
            "identity": {"sourceIp": "203.0.113.9"},
        },
    }
    r = modulo.handler(evento, None)
    return (
        r["statusCode"],
        json.loads(r["body"] or "{}"),
        {k: v[0] for k, v in r.get("multiValueHeaders", {}).items()},
    )


def test_exige_cliente(amb: Ambiente, claims_vendedor: dict[str, str]) -> None:
    assert chamar("POST", "/clientes", None, CORPO)[0] == 401
    assert chamar("POST", "/clientes", claims_vendedor, CORPO)[0] == 403
    assert chamar("GET", "/clientes/meu-perfil", claims_vendedor)[0] == 403


def test_cadastro_mascara_e_nao_persiste_claro(
    amb: Ambiente, caplog: pytest.LogCaptureFixture
) -> None:
    claims = amb.usuario("maria@example.com")
    with caplog.at_level(logging.DEBUG):
        status, corpo, headers = chamar("POST", "/clientes", claims, CORPO)
    assert status == 201
    assert corpo["id"] == claims["sub"]
    assert corpo["cpf"] == "***.***.247-25"
    assert corpo["rg"]["numero"] == "**.***.678-9"
    assert corpo["email"] == "maria@example.com"
    assert corpo["endereco"]["cep"] == "01310100"
    assert corpo["cadastroCompleto"] is True
    assert corpo["camposPendentes"] == []
    assert headers["ETag"] == '"v1"'
    # nada em claro no banco, nem nos logs
    tabela = json.dumps(amb.ddb.scan(TableName="t-clientes")["Items"])
    assert "52998224725" not in tabela
    assert "529.982.247-25" not in tabela
    assert "12.345.678-9" not in tabela
    assert "maria@example.com" not in json.dumps(
        [
            i
            for i in amb.ddb.scan(TableName="t-clientes")["Items"]
            if i["pk"]["S"].startswith(("CPF#", "EMAIL#"))
        ]
    )
    assert "52998224725" not in caplog.text
    assert "529.982.247-25" not in caplog.text


def test_get_me_mascarado_e_perfil_inexistente(amb: Ambiente) -> None:
    claims = amb.usuario("maria@example.com")
    status, corpo, _ = chamar("GET", "/clientes/meu-perfil", claims)
    assert status == 403
    assert corpo["type"] == "urn:revenda:problema:perfil-cliente-inexistente"
    chamar("POST", "/clientes", claims, CORPO)
    status, corpo, headers = chamar("GET", "/clientes/meu-perfil", claims)
    assert status == 200
    assert corpo["cpf"] == "***.***.247-25"
    assert headers["ETag"] == '"v1"'


def test_unicidade_cpf_email_e_duplo_cadastro(amb: Ambiente) -> None:
    a, b = amb.usuario("a@example.com"), amb.usuario("b@example.com")
    assert chamar("POST", "/clientes", a, CORPO)[0] == 201
    assert chamar("POST", "/clientes", a, CORPO)[0] == 409  # mesmo usuario
    status, erro, _ = chamar("POST", "/clientes", b, CORPO)  # mesmo CPF, outro usuario
    assert status == 409
    assert erro["type"] == "urn:revenda:problema:conflito-unicidade"
    outro_cpf = {**CORPO, "cpf": "111.444.777-35"}
    assert chamar("POST", "/clientes", b, outro_cpf)[0] == 201


def test_validacoes_422(amb: Ambiente) -> None:
    claims = amb.usuario("maria@example.com")
    status, erro, _ = chamar("POST", "/clientes", claims, {**CORPO, "cpf": "529.982.247-24"})
    assert status == 422
    assert erro["erros"][0]["campo"] == "cpf"
    recusado = {**CORPO, "consentimento": {**CORPO["consentimento"], "aceito": False}}
    assert chamar("POST", "/clientes", claims, recusado)[0] == 422
    assert chamar("POST", "/clientes", claims, {**CORPO, "id": "x"})[0] == 422  # extra proibido


def test_sem_rg_e_email_nao_verificado_ficam_pendentes(amb: Ambiente) -> None:
    claims = amb.usuario("maria@example.com", verificado=False)
    sem_rg = {k: v for k, v in CORPO.items() if k != "rg"}
    status, corpo, _ = chamar("POST", "/clientes", claims, sem_rg)
    assert status == 201
    assert corpo["cadastroCompleto"] is False
    assert corpo["camposPendentes"] == ["rg", "email"]
    assert corpo["rg"] is None


def test_interno_valida_comprador_e_decifra_cobranca(
    amb: Ambiente, monkeypatch: pytest.MonkeyPatch
) -> None:
    claims = amb.usuario("maria@example.com")
    chamar("POST", "/clientes", claims, CORPO)
    r = interno.handler({"operacao": "VALIDAR_COMPRADOR", "clienteId": claims["sub"]}, None)
    assert r == {"valido": True, "camposPendentes": []}
    assert (
        interno.handler({"operacao": "VALIDAR_COMPRADOR", "clienteId": "nao-existe"}, None)[
            "valido"
        ]
        is False
    )
    cobranca = interno.handler(
        {"operacao": "OBTER_DADOS_COBRANCA", "clienteId": claims["sub"]}, None
    )
    assert cobranca == {"nomeCompleto": "Maria Souza Lima", "cpf": "52998224725"}
    with pytest.raises(ValueError, match="desconhecida"):
        interno.handler({"operacao": "X"}, None)


def test_cifrado_so_abre_com_contexto_correto(amb: Ambiente) -> None:
    claims = amb.usuario("maria@example.com")
    chamar("POST", "/clientes", claims, CORPO)
    item = amb.ddb.get_item(
        TableName="t-clientes",
        Key={"pk": {"S": f"CLIENTE#{claims['sub']}"}, "sk": {"S": "PERFIL"}},
    )["Item"]
    decifrador = DecifradorSealedBox(lambda _v: amb.privada)
    assert (
        decifrador.decifrar(item["cpfCifrado"]["S"], cliente_id=claims["sub"], campo="cpf")
        == "52998224725"
    )
    with pytest.raises(cripto.ErroDecifragem):  # registro copiado para outro cliente
        decifrador.decifrar(item["cpfCifrado"]["S"], cliente_id="outro", campo="cpf")
