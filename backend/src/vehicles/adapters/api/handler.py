"""fn-veiculos-api: catalogo de veiculos (cadastro, listagem e
detalhe)."""

import os
import re
from collections.abc import Callable
from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Any

import boto3
from aws_lambda_powertools.event_handler import Response
from aws_lambda_powertools.event_handler.openapi.params import Body, Path, Query
from botocore.config import Config
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from shared import pagination as paginacao
from shared import parameters as parametros
from shared.errors import RecursoNaoEncontrado, RequisicaoInvalida
from shared.http import AppRevenda, processar
from shared.security import Papel
from shared.text import normalizar_busca
from vehicles.adapters.dynamodb.repository import DynamoDBVeiculoRepository
from vehicles.application.editing import AlterarAnuncio, EditarVeiculo
from vehicles.application.query import ConsultarVeiculos
from vehicles.application.registration import CadastrarVeiculo
from vehicles.domain.models import (
    Cambio,
    Combustivel,
    FiltroVeiculos,
    NovoVeiculo,
    StatusVeiculo,
    Veiculo,
)

app = AppRevenda("veiculos-api")
CACHE_PUBLICO = "public, max-age=30"
FUNCIONARIOS = (Papel.VENDEDOR, Papel.ADMIN)


class _Modelo(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", str_strip_whitespace=True
    )


class VeiculoEntrada(_Modelo):
    marca: Annotated[str, Field(min_length=1, max_length=60)]
    modelo: Annotated[str, Field(min_length=1, max_length=80)]
    ano_fabricacao: int
    ano_modelo: int
    cor: Annotated[str, Field(min_length=1, max_length=30)]
    preco: Annotated[str, Field(max_length=13, examples=["129900.00"])]
    quilometragem: int
    placa: Annotated[str | None, Field(max_length=7)] = None
    renavam: Annotated[str, Field(max_length=11)]
    chassi: Annotated[str, Field(max_length=17)]
    combustivel: Combustivel | None = None
    cambio: Cambio | None = None
    descricao: Annotated[str | None, Field(max_length=2000)] = None


class VeiculoEdicao(_Modelo):
    """PATCH parcial: so os campos enviados (e nao nulos) mudam."""

    marca: Annotated[str | None, Field(min_length=1, max_length=60)] = None
    modelo: Annotated[str | None, Field(min_length=1, max_length=80)] = None
    ano_fabricacao: int | None = None
    ano_modelo: int | None = None
    cor: Annotated[str | None, Field(min_length=1, max_length=30)] = None
    preco: Annotated[str | None, Field(max_length=13)] = None
    quilometragem: int | None = None
    placa: Annotated[str | None, Field(max_length=7)] = None
    renavam: Annotated[str | None, Field(max_length=11)] = None
    chassi: Annotated[str | None, Field(max_length=17)] = None
    combustivel: Combustivel | None = None
    cambio: Cambio | None = None
    descricao: Annotated[str | None, Field(max_length=2000)] = None


@lru_cache(maxsize=1)
def _repositorio() -> DynamoDBVeiculoRepository:
    cliente = boto3.client(
        "dynamodb", config=Config(retries={"mode": "standard", "max_attempts": 5})
    )
    return DynamoDBVeiculoRepository(cliente, os.environ["VEICULOS_TABELA"])


def _publico(v: Veiculo) -> dict[str, Any]:
    return {
        "id": v.id,
        "marca": v.marca,
        "modelo": v.modelo,
        "anoFabricacao": v.ano_fabricacao,
        "anoModelo": v.ano_modelo,
        "cor": v.cor,
        "preco": v.preco,
        "quilometragem": v.quilometragem,
        "placa": v.placa_mascarada,
        "combustivel": v.combustivel.value if v.combustivel else None,
        "cambio": v.cambio.value if v.cambio else None,
        "status": v.status.value,
    }


def _completo(v: Veiculo) -> dict[str, Any]:
    return {
        **_publico(v),
        "placa": v.placa,
        "renavam": v.renavam,
        "chassi": v.chassi,
        "descricao": v.descricao,
        "versao": v.versao,
        "criadoEm": v.criado_em,
        "atualizadoEm": v.atualizado_em,
    }


@app.rota("POST", "/veiculos", *FUNCIONARIOS, summary="Cadastrar veiculo", tags=["Veiculos"])
def cadastrar_veiculo(corpo: Annotated[VeiculoEntrada, Body()]) -> Response[dict[str, Any]]:
    novo = NovoVeiculo(
        marca=corpo.marca,
        modelo=corpo.modelo,
        ano_fabricacao=corpo.ano_fabricacao,
        ano_modelo=corpo.ano_modelo,
        cor=corpo.cor,
        preco=corpo.preco,
        quilometragem=corpo.quilometragem,
        renavam=corpo.renavam,
        chassi=corpo.chassi,
        placa=corpo.placa,
        combustivel=corpo.combustivel,
        cambio=corpo.cambio,
        descricao=corpo.descricao,
    )
    criado = CadastrarVeiculo(_repositorio()).executar(novo, app.identidade().sub)
    return Response(
        status_code=201,
        content_type="application/json",
        headers={"Location": f"/v1/veiculos/{criado.id}", "ETag": f'"v{criado.versao}"'},
        body=_completo(criado),
    )


def _filtro(
    marca: str | None,
    modelo: str | None,
    ano_min: int | None,
    ano_max: int | None,
    preco_min: str | None,
    preco_max: str | None,
) -> FiltroVeiculos:
    for campo, valor in (("precoMin", preco_min), ("precoMax", preco_max)):
        if valor is not None and not re.fullmatch(r"\d{1,10}(\.\d{1,2})?", valor):
            raise RequisicaoInvalida(f"{campo} deve ser decimal (ex.: 50000.00)")

    def centavos(valor: str | None) -> int | None:
        return None if valor is None else int((Decimal(valor) * 100).to_integral_value())

    return FiltroVeiculos(
        marca=normalizar_busca(marca.strip()) if marca else None,
        modelo=normalizar_busca(modelo.strip()) if modelo else None,
        ano_min=ano_min,
        ano_max=ano_max,
        preco_min_centavos=centavos(preco_min),
        preco_max_centavos=centavos(preco_max),
    )


def _pagina(
    status: StatusVeiculo,
    limit: str | None,
    next_token: str | None,
    filtro: FiltroVeiculos,
    visao: Callable[[Veiculo], dict[str, Any]],
    *,
    publico: bool,
) -> Response[dict[str, Any]]:
    segredo = parametros.segredo_cursor()
    cursor = paginacao.decodificar_cursor(next_token, segredo) if next_token else None
    itens, proxima = ConsultarVeiculos(_repositorio()).listar(
        status, limite=paginacao.validar_limite(limit), cursor=cursor, filtro=filtro
    )
    return Response(
        status_code=200,
        content_type="application/json",
        headers={"Cache-Control": CACHE_PUBLICO} if publico else {},
        body={
            "itens": [visao(v) for v in itens],
            "nextToken": paginacao.codificar(proxima, segredo) if proxima else None,
        },
    )


Marca = Annotated[str | None, Query(max_length=60)]
Modelo = Annotated[str | None, Query(max_length=80)]
AnoMin = Annotated[int | None, Query(alias="anoMin", ge=1950, le=2100)]
AnoMax = Annotated[int | None, Query(alias="anoMax", ge=1950, le=2100)]
PrecoMin = Annotated[str | None, Query(alias="precoMin", max_length=13)]
PrecoMax = Annotated[str | None, Query(alias="precoMax", max_length=13)]
Limit = Annotated[str | None, Query()]
NextToken = Annotated[str | None, Query(alias="nextToken")]


@app.rota(
    "GET",
    "/veiculos",
    Papel.ANONIMO,
    summary="Listar veiculos a venda (preco crescente)",
    tags=["Veiculos"],
)
def listar_veiculos(
    limit: Limit = None,
    next_token: NextToken = None,
    marca: Marca = None,
    modelo: Modelo = None,
    ano_min: AnoMin = None,
    ano_max: AnoMax = None,
    preco_min: PrecoMin = None,
    preco_max: PrecoMax = None,
    ordenar: Annotated[str, Query()] = "preco_asc",
    status: Annotated[str, Query()] = "DISPONIVEL",
) -> Response[dict[str, Any]]:
    if ordenar != "preco_asc" or status != "DISPONIVEL":
        raise RequisicaoInvalida("ordenar aceita so preco_asc e status so DISPONIVEL")
    filtro = _filtro(marca, modelo, ano_min, ano_max, preco_min, preco_max)
    return _pagina(StatusVeiculo.DISPONIVEL, limit, next_token, filtro, _publico, publico=True)


@app.rota(
    "GET",
    "/veiculos/vendidos",
    *FUNCIONARIOS,
    summary="Listar veiculos vendidos (preco crescente)",
    tags=["Veiculos"],
)
def listar_vendidos(
    limit: Limit = None,
    next_token: NextToken = None,
    marca: Marca = None,
    modelo: Modelo = None,
    ano_min: AnoMin = None,
    ano_max: AnoMax = None,
    preco_min: PrecoMin = None,
    preco_max: PrecoMax = None,
) -> Response[dict[str, Any]]:
    filtro = _filtro(marca, modelo, ano_min, ano_max, preco_min, preco_max)
    return _pagina(StatusVeiculo.VENDIDO, limit, next_token, filtro, _publico, publico=False)


@app.rota(
    "GET", "/veiculos/<veiculo_id>", Papel.ANONIMO, summary="Detalhar veiculo", tags=["Veiculos"]
)
def obter_veiculo(veiculo_id: Annotated[str, Path()]) -> Response[dict[str, Any]]:
    if len(veiculo_id) > 36:  # noqa: PLR2004
        raise RecursoNaoEncontrado("Veiculo nao encontrado.")
    veiculo = ConsultarVeiculos(_repositorio()).obter_publico(veiculo_id)
    return Response(
        status_code=200,
        content_type="application/json",
        headers={"Cache-Control": CACHE_PUBLICO, "ETag": f'"v{veiculo.versao}"'},
        body={**_publico(veiculo), "descricao": veiculo.descricao},
    )


def _com_etag(veiculo: Veiculo) -> Response[dict[str, Any]]:
    return Response(
        status_code=200,
        content_type="application/json",
        headers={"ETag": f'"v{veiculo.versao}"'},
        body=_completo(veiculo),
    )


@app.rota(
    "PATCH",
    "/veiculos/<veiculo_id>",
    *FUNCIONARIOS,
    summary="Editar veiculo (If-Match)",
    tags=["Veiculos"],
)
def editar_veiculo(
    veiculo_id: Annotated[str, Path()], corpo: Annotated[VeiculoEdicao, Body()]
) -> Response[dict[str, Any]]:
    versao = app.versao_if_match()
    mudancas = corpo.model_dump(exclude_unset=True, exclude_none=True)
    return _com_etag(EditarVeiculo(_repositorio()).executar(veiculo_id, mudancas, versao))


@app.rota(
    "POST",
    "/veiculos/<veiculo_id>/inativacao",
    *FUNCIONARIOS,
    summary="Inativar anuncio",
    tags=["Veiculos"],
)
def inativar_veiculo(veiculo_id: Annotated[str, Path()]) -> Response[dict[str, Any]]:
    return _com_etag(AlterarAnuncio(_repositorio()).inativar(veiculo_id, app.versao_if_match()))


@app.rota(
    "POST",
    "/veiculos/<veiculo_id>/reativacao",
    *FUNCIONARIOS,
    summary="Reativar anuncio",
    tags=["Veiculos"],
)
def reativar_veiculo(veiculo_id: Annotated[str, Path()]) -> Response[dict[str, Any]]:
    return _com_etag(AlterarAnuncio(_repositorio()).reativar(veiculo_id, app.versao_if_match()))


@app.rota(
    "GET",
    "/gestao/veiculos",
    *FUNCIONARIOS,
    summary="Listar veiculos (visao de gestao)",
    tags=["Gestao"],
)
def listar_gestao(
    limit: Limit = None,
    next_token: NextToken = None,
    marca: Marca = None,
    modelo: Modelo = None,
    ano_min: AnoMin = None,
    ano_max: AnoMax = None,
    preco_min: PrecoMin = None,
    preco_max: PrecoMax = None,
    status: Annotated[StatusVeiculo, Query()] = StatusVeiculo.DISPONIVEL,
) -> Response[dict[str, Any]]:
    filtro = _filtro(marca, modelo, ano_min, ano_max, preco_min, preco_max)
    return _pagina(status, limit, next_token, filtro, _completo, publico=False)


@app.rota(
    "GET",
    "/gestao/veiculos/<veiculo_id>",
    *FUNCIONARIOS,
    summary="Detalhar veiculo (visao de gestao)",
    tags=["Gestao"],
)
def obter_gestao(veiculo_id: Annotated[str, Path()]) -> Response[dict[str, Any]]:
    if len(veiculo_id) > 36:  # noqa: PLR2004
        raise RecursoNaoEncontrado("Veiculo nao encontrado.")
    return _com_etag(ConsultarVeiculos(_repositorio()).obter_completo(veiculo_id))


def handler(evento: dict[str, Any], contexto: Any) -> dict[str, Any]:
    return processar(app, evento, contexto)
