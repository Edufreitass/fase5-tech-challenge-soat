import pytest

from shared.errors import ErroValidacao
from shared.text import normalizar_busca
from vehicles.domain.models import NovoVeiculo, formatar_preco
from vehicles.domain.validation import (
    digito_renavam,
    renavam_valido,
    validar_e_normalizar,
)


def novo(**kw: object) -> NovoVeiculo:
    base = {
        "marca": " Volkswagen ",
        "modelo": "T-Cross",
        "ano_fabricacao": 2023,
        "ano_modelo": 2024,
        "cor": "Cinza",
        "preco": "129900.00",
        "quilometragem": 100,
        "renavam": "09000079190",
        "chassi": "9bxdmk01a00000370",
        "placa": "bra2e19",
    }
    return NovoVeiculo(**{**base, **kw})  # type: ignore[arg-type]


def test_normaliza_campos() -> None:
    v = validar_e_normalizar(novo())
    assert v.marca == "Volkswagen"
    assert v.chassi == "9BXDMK01A00000370"
    assert v.placa == "BRA2E19"


def test_renavam_dv() -> None:
    assert renavam_valido("09000079190")
    assert not renavam_valido("09000079191")
    assert not renavam_valido("123")
    assert digito_renavam("0900007919") == 0


@pytest.mark.parametrize(
    ("campo", "valor", "esperado"),
    [
        ("marca", "", "marca"),
        ("ano_fabricacao", 1900, "anoFabricacao"),
        ("ano_modelo", 2030, "anoModelo"),
        ("quilometragem", -1, "quilometragem"),
        ("preco", "0.00", "preco"),
        ("preco", "12,5", "preco"),
        ("preco", "abc", "preco"),
        ("placa", "123", "placa"),
        ("chassi", "OOOOOOOOOOOOOOOOO", "chassi"),
        ("renavam", "12345678901", "renavam"),
        ("descricao", "x" * 2001, "descricao"),
    ],
)
def test_invalidos(campo: str, valor: object, esperado: str) -> None:
    with pytest.raises(ErroValidacao) as exc:
        validar_e_normalizar(novo(**{campo: valor}))
    assert esperado in [e["campo"] for e in exc.value.extras["erros"]]


def test_busca_sem_acento_e_preco() -> None:
    assert normalizar_busca("Citroën Ágil") == "citroen agil"
    assert formatar_preco(12990005) == "129900.05"
