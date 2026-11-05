"""Repositorio DynamoDB de veiculos (tabela `veiculos`, GSI
`gsi_status_preco`)."""

from decimal import Decimal
from typing import Any

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

from shared.contracts import Cursor
from shared.dynamo import transacionar
from shared.errors import ConflitoUnicidade, VersaoDesatualizada
from vehicles.domain.models import Cambio, Combustivel, FiltroVeiculos, StatusVeiculo, Veiculo

GSI = "gsi_status_preco"
MAX_CONSULTAS = 5
_SER = TypeSerializer()
_DES = TypeDeserializer()


def _ser(item: dict[str, Any]) -> dict[str, Any]:
    return {k: _SER.serialize(v) for k, v in item.items() if v is not None}


def _des(item: dict[str, Any]) -> dict[str, Any]:
    return {k: _DES.deserialize(v) for k, v in item.items()}


def chave_gsi(status: StatusVeiculo, preco_centavos: int, veiculo_id: str) -> tuple[str, str]:
    return f"STATUS#{status.value}", f"{preco_centavos:013d}#{veiculo_id}"


def para_item(v: Veiculo) -> dict[str, Any]:
    gsi1pk, gsi1sk = chave_gsi(v.status, v.preco_centavos, v.id)
    return {
        "pk": f"VEICULO#{v.id}",
        "sk": "META",
        "tipo": "VEICULO",
        "id": v.id,
        "marca": v.marca,
        "marcaBusca": v.marca_busca,
        "modelo": v.modelo,
        "modeloBusca": v.modelo_busca,
        "anoFabricacao": v.ano_fabricacao,
        "anoModelo": v.ano_modelo,
        "cor": v.cor,
        "precoCentavos": v.preco_centavos,
        "quilometragem": v.quilometragem,
        "placa": v.placa,
        "renavam": v.renavam,
        "chassi": v.chassi,
        "combustivel": v.combustivel.value if v.combustivel else None,
        "cambio": v.cambio.value if v.cambio else None,
        "descricao": v.descricao,
        "status": v.status.value,
        "versao": v.versao,
        "vendaAtualId": v.venda_atual_id,
        "criadoEm": v.criado_em,
        "atualizadoEm": v.atualizado_em,
        "criadoPor": v.criado_por,
        "gsi1pk": gsi1pk,
        "gsi1sk": gsi1sk,
    }


def de_item(i: dict[str, Any]) -> Veiculo:
    def inteiro(chave: str) -> int:
        return int(i[chave]) if isinstance(i[chave], Decimal) else i[chave]

    return Veiculo(
        id=i["id"],
        marca=i["marca"],
        marca_busca=i["marcaBusca"],
        modelo=i["modelo"],
        modelo_busca=i["modeloBusca"],
        ano_fabricacao=inteiro("anoFabricacao"),
        ano_modelo=inteiro("anoModelo"),
        cor=i["cor"],
        preco_centavos=inteiro("precoCentavos"),
        quilometragem=inteiro("quilometragem"),
        renavam=i["renavam"],
        chassi=i["chassi"],
        status=StatusVeiculo(i["status"]),
        versao=inteiro("versao"),
        criado_em=i["criadoEm"],
        atualizado_em=i["atualizadoEm"],
        criado_por=i["criadoPor"],
        placa=i.get("placa"),
        combustivel=Combustivel(i["combustivel"]) if i.get("combustivel") else None,
        cambio=Cambio(i["cambio"]) if i.get("cambio") else None,
        descricao=i.get("descricao"),
        venda_atual_id=i.get("vendaAtualId"),
    )


class DynamoDBVeiculoRepository:
    def __init__(self, cliente: Any, tabela: str) -> None:
        self._ddb = cliente
        self._tabela = tabela

    def criar(self, veiculo: Veiculo) -> None:
        unicos = [f"CHASSI#{veiculo.chassi}", f"RENAVAM#{veiculo.renavam}"]
        if veiculo.placa:
            unicos.append(f"PLACA#{veiculo.placa}")
        itens: list[dict[str, Any]] = [
            {
                "Put": {
                    "TableName": self._tabela,
                    "Item": _ser(para_item(veiculo)),
                    "ConditionExpression": "attribute_not_exists(pk)",
                }
            }
        ]
        itens += [
            {
                "Put": {
                    "TableName": self._tabela,
                    "Item": _ser({"pk": pk, "sk": "UNIQ", "veiculoId": veiculo.id}),
                    "ConditionExpression": "attribute_not_exists(pk)",
                }
            }
            for pk in unicos
        ]
        try:
            transacionar(self._ddb, itens)
        except self._ddb.exceptions.TransactionCanceledException as erro:
            raise ConflitoUnicidade("Chassi, RENAVAM ou placa ja cadastrado.") from erro

    def obter(self, veiculo_id: str) -> Veiculo | None:
        resposta = self._ddb.get_item(
            TableName=self._tabela,
            Key=_ser({"pk": f"VEICULO#{veiculo_id}", "sk": "META"}),
            ConsistentRead=True,
        )
        return de_item(_des(resposta["Item"])) if "Item" in resposta else None

    def listar_por_status(
        self,
        status: StatusVeiculo,
        *,
        limite: int,
        cursor: Cursor | None,
        filtro: FiltroVeiculos | None = None,
    ) -> tuple[list[Veiculo], Cursor | None]:
        """Ordenado por preco crescente (GSI). Preco vai na
        KeyCondition;
        demais filtros em
        FilterExpression, por isso ate 5 consultas internas preenchem
        `limite`.
        """
        filtro = filtro or FiltroVeiculos()
        chave = "gsi1pk = :p"
        valores: dict[str, Any] = {":p": f"STATUS#{status.value}"}
        if filtro.preco_min_centavos is not None or filtro.preco_max_centavos is not None:
            minimo = filtro.preco_min_centavos or 0
            maximo = (
                filtro.preco_max_centavos
                if filtro.preco_max_centavos is not None
                else 9_999_999_999_999
            )
            chave += " AND gsi1sk BETWEEN :lo AND :hi"
            valores[":lo"] = f"{minimo:013d}"
            valores[":hi"] = f"{maximo:013d}#~"  # '~' > qualquer caractere do UUID
        filtros: list[str] = []
        if filtro.marca:
            filtros.append("contains(marcaBusca, :marca)")
            valores[":marca"] = filtro.marca
        if filtro.modelo:
            filtros.append("contains(modeloBusca, :modelo)")
            valores[":modelo"] = filtro.modelo
        if filtro.ano_min is not None:
            filtros.append("anoModelo >= :amin")
            valores[":amin"] = filtro.ano_min
        if filtro.ano_max is not None:
            filtros.append("anoModelo <= :amax")
            valores[":amax"] = filtro.ano_max
        parametros: dict[str, Any] = {
            "TableName": self._tabela,
            "IndexName": GSI,
            "KeyConditionExpression": chave,
            "ExpressionAttributeValues": _ser(valores),
            "ScanIndexForward": True,
            "Limit": limite + 1,
        }
        if filtros:
            parametros["FilterExpression"] = " AND ".join(filtros)
        inicio = cursor
        itens: list[dict[str, Any]] = []
        ultima: dict[str, Any] | None = None
        for _ in range(MAX_CONSULTAS if filtros else 1):
            if inicio:
                parametros["ExclusiveStartKey"] = _ser(inicio)
            resposta = self._ddb.query(**parametros)
            itens += [_des(i) for i in resposta["Items"]]
            ultima = (
                _des(resposta["LastEvaluatedKey"]) if resposta.get("LastEvaluatedKey") else None
            )
            if len(itens) > limite or ultima is None:
                break
            inicio = ultima
        proxima = None
        if len(itens) > limite:
            itens = itens[:limite]
            ultimo = itens[-1]
            proxima = {k: ultimo[k] for k in ("pk", "sk", "gsi1pk", "gsi1sk")}
        elif ultima is not None:
            proxima = ultima  # consultas internas esgotadas: o cliente continua daqui
        return [de_item(i) for i in itens], proxima

    # -- edicao e anuncio
    # ----------------------------------------------------------
    def atualizar(self, atual: Veiculo, novo: Veiculo) -> None:
        condicao = "versao = :v AND #s = :st"
        valores = _ser({":v": atual.versao, ":st": atual.status.value})
        itens: list[dict[str, Any]] = [
            {
                "Put": {
                    "TableName": self._tabela,
                    "Item": _ser(para_item(novo)),
                    "ConditionExpression": condicao,
                    "ExpressionAttributeNames": {"#s": "status"},
                    "ExpressionAttributeValues": valores,
                }
            }
        ]
        trocas = [
            ("CHASSI", atual.chassi, novo.chassi),
            ("RENAVAM", atual.renavam, novo.renavam),
            ("PLACA", atual.placa, novo.placa),
        ]
        for tipo, antigo, atualizado in trocas:
            if atualizado is None or antigo == atualizado:
                continue
            if antigo is not None:
                itens.append(
                    {
                        "Delete": {
                            "TableName": self._tabela,
                            "Key": _ser({"pk": f"{tipo}#{antigo}", "sk": "UNIQ"}),
                            "ConditionExpression": "veiculoId = :id",
                            "ExpressionAttributeValues": _ser({":id": atual.id}),
                        }
                    }
                )
            itens.append(
                {
                    "Put": {
                        "TableName": self._tabela,
                        "Item": _ser(
                            {"pk": f"{tipo}#{atualizado}", "sk": "UNIQ", "veiculoId": atual.id}
                        ),
                        "ConditionExpression": "attribute_not_exists(pk)",
                    }
                }
            )
        try:
            transacionar(self._ddb, itens)
        except self._ddb.exceptions.TransactionCanceledException as erro:
            motivos = erro.response.get("CancellationReasons", [])
            if motivos and motivos[0].get("Code") == "ConditionalCheckFailed":
                raise VersaoDesatualizada(
                    "O veiculo foi alterado; releia e tente de novo."
                ) from erro
            raise ConflitoUnicidade("Chassi, RENAVAM ou placa ja cadastrado.") from erro

    def alterar_status(self, atual: Veiculo, novo_status: StatusVeiculo, agora: str) -> None:
        gsi1pk, _ = chave_gsi(novo_status, atual.preco_centavos, atual.id)
        ok = self._atualizar(
            atual.id,
            "SET #s = :n, versao = versao + :um, gsi1pk = :g, atualizadoEm = :t",
            {
                ":n": novo_status.value,
                ":um": 1,
                ":g": gsi1pk,
                ":t": agora,
                ":v": atual.versao,
                ":st": atual.status.value,
            },
            "versao = :v AND #s = :st",
        )
        if not ok:
            raise VersaoDesatualizada("O veiculo foi alterado; releia e tente de novo.")

    # -- transicoes da saga: condicionais e idempotentes
    # -----------------
    def _atualizar(
        self, veiculo_id: str, expressao: str, valores: dict[str, Any], condicao: str
    ) -> bool:
        try:
            self._ddb.update_item(
                TableName=self._tabela,
                Key=_ser({"pk": f"VEICULO#{veiculo_id}", "sk": "META"}),
                UpdateExpression=expressao,
                ConditionExpression=condicao,
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues=_ser(valores),
            )
        except self._ddb.exceptions.ConditionalCheckFailedException:
            return False
        return True

    def liberar(self, veiculo_id: str, venda_id: str, agora: str) -> None:
        """-> DISPONIVEL. Ja liberado ou de outra venda = sucesso."""
        self._atualizar(
            veiculo_id,
            (
                "SET #s = :d, versao = versao + :um, gsi1pk = :g, atualizadoE"
                "m = :t REMOVE vendaAtualId"
            ),
            {
                ":d": "DISPONIVEL",
                ":um": 1,
                ":g": "STATUS#DISPONIVEL",
                ":t": agora,
                ":v": venda_id,
                ":r": "RESERVADO",
                ":a": "AGUARDANDO_RETIRADA",
            },
            "vendaAtualId = :v AND #s IN (:r, :a)",
        )

    def aguardar_retirada(self, veiculo_id: str, venda_id: str, agora: str) -> bool:
        ok = self._atualizar(
            veiculo_id,
            "SET #s = :n, versao = versao + :um, gsi1pk = :g, atualizadoEm = :t",
            {
                ":n": "AGUARDANDO_RETIRADA",
                ":um": 1,
                ":g": "STATUS#AGUARDANDO_RETIRADA",
                ":t": agora,
                ":v": venda_id,
                ":r": "RESERVADO",
            },
            "vendaAtualId = :v AND #s = :r",
        )
        if ok:
            return True
        atual = self.obter(veiculo_id)
        return (
            atual is not None
            and atual.venda_atual_id == venda_id
            and atual.status == StatusVeiculo.AGUARDANDO_RETIRADA
        )

    def baixar(self, veiculo_id: str, venda_id: str, agora: str) -> bool:
        ok = self._atualizar(
            veiculo_id,
            "SET #s = :n, versao = versao + :um, gsi1pk = :g, atualizadoEm = :t",
            {
                ":n": "VENDIDO",
                ":um": 1,
                ":g": "STATUS#VENDIDO",
                ":t": agora,
                ":v": venda_id,
                ":a": "AGUARDANDO_RETIRADA",
            },
            "vendaAtualId = :v AND #s = :a",
        )
        if ok:
            return True
        atual = self.obter(veiculo_id)
        return (
            atual is not None
            and atual.venda_atual_id == venda_id
            and atual.status == StatusVeiculo.VENDIDO
        )
