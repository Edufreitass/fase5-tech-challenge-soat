"""Criacao das tabelas DynamoDB (moto) com o mesmo desenho do
Terraform.
"""

from typing import Any


def _attrs(*nomes: str) -> list[dict[str, str]]:
    return [{"AttributeName": n, "AttributeType": "S"} for n in nomes]


def _gsi(nome: str, hash_key: str, range_key: str) -> dict[str, Any]:
    return {
        "IndexName": nome,
        "KeySchema": [
            {"AttributeName": hash_key, "KeyType": "HASH"},
            {"AttributeName": range_key, "KeyType": "RANGE"},
        ],
        "Projection": {"ProjectionType": "ALL"},
    }


def criar_tabelas(ddb: Any) -> None:
    pk_sk = [
        {"AttributeName": "pk", "KeyType": "HASH"},
        {"AttributeName": "sk", "KeyType": "RANGE"},
    ]
    comum = {"BillingMode": "PAY_PER_REQUEST"}
    ddb.create_table(
        TableName="t-veiculos",
        AttributeDefinitions=_attrs("pk", "sk", "gsi1pk", "gsi1sk"),
        KeySchema=pk_sk,
        GlobalSecondaryIndexes=[_gsi("gsi_status_preco", "gsi1pk", "gsi1sk")],
        **comum,
    )
    ddb.create_table(
        TableName="t-vendas",
        AttributeDefinitions=_attrs("pk", "sk", "gsi1pk", "gsi1sk", "gsi2pk", "gsi2sk"),
        KeySchema=pk_sk,
        GlobalSecondaryIndexes=[
            _gsi("gsi_cliente", "gsi1pk", "gsi1sk"),
            _gsi("gsi_status", "gsi2pk", "gsi2sk"),
        ],
        **comum,
    )
    ddb.create_table(
        TableName="t-pagamentos", AttributeDefinitions=_attrs("pk", "sk"), KeySchema=pk_sk, **comum
    )
    ddb.create_table(
        TableName="t-idem",
        AttributeDefinitions=_attrs("id"),
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        **comum,
    )
    ddb.create_table(
        TableName="t-mock",
        AttributeDefinitions=_attrs("pk"),
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        **comum,
    )
