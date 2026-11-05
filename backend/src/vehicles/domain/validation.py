"""Regras de validacao do veiculo."""

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from shared.errors import ErroValidacao
from shared.text import normalizar_texto
from vehicles.domain.models import NovoVeiculo

_PLACA = re.compile(r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$")
_CHASSI = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
_RENAVAM = re.compile(r"^[0-9]{11}$")
_PRECO = re.compile(r"^[0-9]{1,10}\.[0-9]{2}$")
PESOS_RENAVAM = (2, 3, 4, 5, 6, 7, 8, 9, 2, 3)


def digito_renavam(primeiros_dez: str) -> int:
    soma = sum(int(d) * p for d, p in zip(reversed(primeiros_dez), PESOS_RENAVAM, strict=True))
    resto = (soma * 10) % 11
    return 0 if resto == 10 else resto  # noqa: PLR2004


def renavam_valido(renavam: str) -> bool:
    return bool(_RENAVAM.match(renavam)) and digito_renavam(renavam[:10]) == int(renavam[10])


def preco_para_centavos(preco: str) -> int:
    try:
        valor = Decimal(preco)
    except InvalidOperation as erro:
        raise ValueError("preco invalido") from erro
    return int(valor * 100)


def validar_e_normalizar(novo: NovoVeiculo) -> NovoVeiculo:
    """Retorna o comando normalizado ou levanta `ErroValidacao` com
    todos
    os erros de campo.
    """
    erros: list[dict[str, str]] = []

    def erro(campo: str, mensagem: str) -> None:
        erros.append({"campo": campo, "mensagem": mensagem})

    marca = normalizar_texto(novo.marca)
    modelo = normalizar_texto(novo.modelo)
    cor = normalizar_texto(novo.cor)
    descricao = normalizar_texto(novo.descricao) if novo.descricao else None
    placa = normalizar_texto(novo.placa).upper() if novo.placa else None
    chassi = normalizar_texto(novo.chassi).upper()
    renavam = normalizar_texto(novo.renavam)

    for campo, valor, maximo in (("marca", marca, 60), ("modelo", modelo, 80), ("cor", cor, 30)):
        if not 1 <= len(valor) <= maximo:
            erro(campo, f"deve ter entre 1 e {maximo} caracteres")
    if descricao is not None and len(descricao) > 2000:  # noqa: PLR2004
        erro("descricao", "deve ter no maximo 2000 caracteres")

    ano_limite = datetime.now(UTC).year + 1
    if not 1950 <= novo.ano_fabricacao <= ano_limite:  # noqa: PLR2004
        erro("anoFabricacao", f"deve estar entre 1950 e {ano_limite}")
    if not novo.ano_fabricacao <= novo.ano_modelo <= novo.ano_fabricacao + 1:
        erro("anoModelo", "deve ser o ano de fabricacao ou o seguinte")
    if novo.quilometragem < 0:
        erro("quilometragem", "deve ser maior ou igual a zero")
    if not _PRECO.match(novo.preco) or preco_para_centavos(novo.preco) <= 0:
        erro("preco", "deve ser decimal positivo com duas casas (ex.: 89900.00)")
    if placa is not None and not _PLACA.match(placa):
        erro("placa", "formato invalido (ex.: BRA2E19)")
    if not _CHASSI.match(chassi):
        erro("chassi", "deve ter 17 caracteres alfanumericos, sem I, O e Q")
    if not renavam_valido(renavam):
        erro("renavam", "deve ter 11 digitos com digito verificador valido")

    if erros:
        raise ErroValidacao(erros)
    return NovoVeiculo(
        marca=marca,
        modelo=modelo,
        ano_fabricacao=novo.ano_fabricacao,
        ano_modelo=novo.ano_modelo,
        cor=cor,
        preco=novo.preco,
        quilometragem=novo.quilometragem,
        renavam=renavam,
        chassi=chassi,
        placa=placa,
        combustivel=novo.combustivel,
        cambio=novo.cambio,
        descricao=descricao,
    )
