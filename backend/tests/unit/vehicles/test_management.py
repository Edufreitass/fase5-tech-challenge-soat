"""Veiculos: edicao (If-Match), inativacao, vendidos, gestao e
filtros."""

from typing import Any

from tests.unit.vehicles.test_api import CORPO, cadastrar, chamar, renavam, repo  # noqa: F401
from vehicles.adapters.dynamodb.repository import DynamoDBVeiculoRepository
from vehicles.application.registration import CadastrarVeiculo
from vehicles.domain.models import NovoVeiculo, StatusVeiculo


def criar(
    repo: DynamoDBVeiculoRepository,
    n: int,
    preco: str,
    marca: str = "Fiat",
    modelo: str = "Uno",
    ano: int = 2022,
    **kw: Any,
) -> str:
    novo = NovoVeiculo(
        marca,
        f"{modelo} {n}",
        ano,
        ano,
        "Branco",
        preco,
        10,
        renavam(n),
        f"9BXDMK{n:011d}",
        placa=kw.get("placa"),
    )
    return CadastrarVeiculo(repo).executar(novo, "t").id


def com_if_match(
    metodo: str, caminho: str, claims: dict[str, str], corpo: Any, versao: str | None
) -> tuple[int, Any, dict[str, str]]:
    import json

    evento = {
        "httpMethod": metodo,
        "path": caminho,
        "resource": caminho,
        "headers": {"If-Match": versao} if versao else {},
        "multiValueHeaders": {},
        "queryStringParameters": None,
        "body": json.dumps(corpo) if corpo is not None else None,
        "isBase64Encoded": False,
        "requestContext": {"authorizer": {"claims": claims}, "requestId": "r", "stage": "v1"},
    }
    from vehicles.adapters.api import handler as modulo

    r = modulo.handler(evento, None)
    return (
        r["statusCode"],
        json.loads(r["body"] or "{}"),
        {k: v[0] for k, v in r.get("multiValueHeaders", {}).items()},
    )


def test_patch_exige_if_match_e_versao_correta(repo, claims_vendedor) -> None:  # type: ignore[no-untyped-def]
    vid = criar(repo, 1, "1000.00")
    caminho = f"/veiculos/{vid}"
    assert com_if_match("PATCH", caminho, claims_vendedor, {"cor": "Preto"}, None)[0] == 428
    assert com_if_match("PATCH", caminho, claims_vendedor, {"cor": "Preto"}, "lixo")[0] == 400
    status, corpo, _ = com_if_match("PATCH", caminho, claims_vendedor, {"cor": "Preto"}, '"v9"')
    assert (status, corpo["type"]) == (412, "urn:revenda:problema:versao-desatualizada")
    status, corpo, headers = com_if_match(
        "PATCH", caminho, claims_vendedor, {"cor": "Preto", "preco": "2500.50"}, '"v1"'
    )
    assert status == 200
    assert (corpo["cor"], corpo["preco"], corpo["versao"], headers["ETag"]) == (
        "Preto",
        "2500.50",
        2,
        '"v2"',
    )
    assert (
        com_if_match("PATCH", caminho, claims_vendedor, {"cor": "Azul"}, '"v1"')[0] == 412
    )  # versao ja consumida
    assert (
        com_if_match("PATCH", caminho, claims_vendedor, {"id": "x"}, '"v2"')[0] == 422
    )  # campo desconhecido


def test_patch_reordena_na_listagem_e_atualiza_busca(repo, claims_vendedor) -> None:  # type: ignore[no-untyped-def]
    a, b = criar(repo, 1, "1000.00"), criar(repo, 2, "2000.00")
    assert [i["id"] for i in chamar("GET", "/veiculos")[1]["itens"]] == [a, b]
    com_if_match(
        "PATCH",
        f"/veiculos/{a}",
        claims_vendedor,
        {"preco": "3000.00", "marca": "Citroën"},
        '"v1"',
    )
    itens = chamar("GET", "/veiculos")[1]["itens"]
    assert [i["id"] for i in itens] == [b, a]  # gsi1sk acompanha o preco
    assert [
        i["id"] for i in chamar("GET", "/veiculos", query={"marca": "citroen"})[1]["itens"]
    ] == [a]


def test_patch_unicidade_e_troca_de_chaves(repo, claims_vendedor) -> None:  # type: ignore[no-untyped-def]
    a, b = criar(repo, 1, "1000.00"), criar(repo, 2, "2000.00")
    status, erro, _ = com_if_match(
        "PATCH", f"/veiculos/{b}", claims_vendedor, {"chassi": f"9BXDMK{1:011d}"}, '"v1"'
    )
    assert (status, erro["type"]) == (409, "urn:revenda:problema:conflito-unicidade")
    novo_chassi = "9BXDMK99999999999"
    assert (
        com_if_match("PATCH", f"/veiculos/{b}", claims_vendedor, {"chassi": novo_chassi}, '"v1"')[
            0
        ]
        == 200
    )
    # o chassi antigo foi liberado e o novo esta ocupado
    assert (
        com_if_match(
            "PATCH", f"/veiculos/{a}", claims_vendedor, {"chassi": f"9BXDMK{2:011d}"}, '"v1"'
        )[0]
        == 200
    )
    assert (
        com_if_match("PATCH", f"/veiculos/{a}", claims_vendedor, {"chassi": novo_chassi}, '"v2"')[
            0
        ]
        == 409
    )


def test_regras_por_status(repo, claims_vendedor) -> None:  # type: ignore[no-untyped-def]
    vid = criar(repo, 1, "1000.00")
    for status in ("RESERVADO", "AGUARDANDO_RETIRADA"):
        repo._ddb.update_item(
            TableName="t-veiculos",
            Key={"pk": {"S": f"VEICULO#{vid}"}, "sk": {"S": "META"}},
            UpdateExpression="SET #s = :s, versao = :v",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": {"S": status}, ":v": {"N": "5"}},
        )
        caminho = f"/veiculos/{vid}"
        for campo, valor in (
            ("preco", "9.00"),
            ("chassi", "9BXDMK00000000042"),
            ("renavam", renavam(77)),
        ):
            assert (
                com_if_match("PATCH", caminho, claims_vendedor, {campo: valor}, '"v5"')[0] == 422
            ), (
                status,
                campo,
            )
        assert com_if_match("PATCH", caminho, claims_vendedor, {"cor": "Verde"}, '"v5"')[0] == 200
        repo._ddb.update_item(
            TableName="t-veiculos",
            Key={"pk": {"S": f"VEICULO#{vid}"}, "sk": {"S": "META"}},
            UpdateExpression="SET versao = :v",
            ExpressionAttributeValues={":v": {"N": "5"}},
        )
    repo._ddb.update_item(
        TableName="t-veiculos",
        Key={"pk": {"S": f"VEICULO#{vid}"}, "sk": {"S": "META"}},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": {"S": "VENDIDO"}},
    )
    assert (
        com_if_match("PATCH", f"/veiculos/{vid}", claims_vendedor, {"cor": "Verde"}, '"v5"')[0]
        == 422
    )  # vendido


def test_inativar_e_reativar(repo, claims_vendedor) -> None:  # type: ignore[no-untyped-def]
    vid = criar(repo, 1, "1000.00")
    assert (
        com_if_match("POST", f"/veiculos/{vid}/reativacao", claims_vendedor, None, '"v1"')[0]
        == 422
    )  # nao esta inativo
    status, corpo, headers = com_if_match(
        "POST", f"/veiculos/{vid}/inativacao", claims_vendedor, None, '"v1"'
    )
    assert (status, corpo["status"], headers["ETag"]) == (200, "INATIVO", '"v2"')
    assert chamar("GET", "/veiculos")[1]["itens"] == []  # sai da listagem publica
    assert chamar("GET", f"/veiculos/{vid}")[0] == 404  # INATIVO nao e publico
    assert (
        com_if_match("POST", f"/veiculos/{vid}/inativacao", claims_vendedor, None, '"v2"')[0]
        == 422
    )
    assert (
        com_if_match("POST", f"/veiculos/{vid}/reativacao", claims_vendedor, None, '"v1"')[0]
        == 412
    )
    assert (
        com_if_match("POST", f"/veiculos/{vid}/reativacao", claims_vendedor, None, '"v2"')[1][
            "status"
        ]
        == "DISPONIVEL"
    )
    assert [i["id"] for i in chamar("GET", "/veiculos")[1]["itens"]] == [vid]


def test_filtros_da_listagem(repo) -> None:  # type: ignore[no-untyped-def]
    criar(repo, 1, "10000.00", "Volkswagen", "Gol", 2018)
    criar(repo, 2, "20000.00", "Volkswagen", "Polo", 2021)
    criar(repo, 3, "30000.00", "Fiat", "Argo", 2022)
    criar(repo, 4, "40000.00", "Fiat", "Pálio", 2022)

    def modelos(**q: str) -> list[str]:
        status, corpo, _ = chamar("GET", "/veiculos", query=q)
        assert status == 200
        return [i["modelo"].split()[0] for i in corpo["itens"]]

    assert modelos(marca="volks") == ["Gol", "Polo"]
    assert modelos(modelo="palio") == ["Pálio"]  # sem acento e sem diferenciar maiusculas
    assert modelos(anoMin="2021") == ["Polo", "Argo", "Pálio"]
    assert modelos(anoMax="2021") == ["Gol", "Polo"]
    assert modelos(precoMin="20000.00", precoMax="30000.00") == ["Polo", "Argo"]
    assert modelos(precoMax="19999.99") == ["Gol"]
    assert modelos(marca="fiat", anoMin="2022", precoMin="35000") == ["Pálio"]
    assert chamar("GET", "/veiculos", query={"precoMin": "abc"})[0] == 400


def test_filtro_com_paginacao_preenche_o_limite(repo) -> None:  # type: ignore[no-untyped-def]
    for n in range(1, 13):  # so os pares sao Fiat; o filtro descarta metade de cada consulta
        criar(repo, n, f"{n * 1000}.00", "Fiat" if n % 2 == 0 else "Ford", "Mod")
    coletados: list[str] = []
    token = None
    while True:
        q = {"marca": "fiat", "limit": "2", **({"nextToken": token} if token else {})}
        status, corpo, _ = chamar("GET", "/veiculos", query=q)
        assert status == 200
        coletados += [i["preco"] for i in corpo["itens"]]
        token = corpo["nextToken"]
        if not token:
            break
    assert coletados == [f"{n * 1000}.00" for n in range(2, 13, 2)]


def test_vendidos_e_gestao_exigem_funcionario(repo, claims_cliente, claims_vendedor) -> None:  # type: ignore[no-untyped-def]
    vid = criar(repo, 1, "1000.00")
    criar(repo, 2, "2000.00")
    repo.alterar_status(repo.obter(vid), StatusVeiculo.INATIVO, "2026-10-18T00:00:00.000Z")
    for caminho in ("/veiculos/vendidos", "/gestao/veiculos", f"/gestao/veiculos/{vid}"):
        assert chamar("GET", caminho, None)[0] == 401
        assert chamar("GET", caminho, claims_cliente)[0] == 403
    status, corpo, _ = chamar(
        "GET", "/gestao/veiculos", claims_vendedor, query={"status": "INATIVO"}
    )
    assert status == 200
    assert [i["id"] for i in corpo["itens"]] == [vid]
    assert corpo["itens"][0]["renavam"] == renavam(1)  # visao completa
    status, corpo, headers = chamar("GET", f"/gestao/veiculos/{vid}", claims_vendedor)
    assert (status, corpo["status"], headers["ETag"]) == (200, "INATIVO", '"v2"')
    assert chamar("GET", "/veiculos/vendidos", claims_vendedor)[1]["itens"] == []
    assert chamar("GET", "/gestao/veiculos", claims_vendedor, query={"status": "XYZ"})[0] == 422
