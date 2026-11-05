from datetime import date

import pytest

from customers.domain import rules as regras
from customers.domain.brazilian_tax_id import cpf_valido, somente_digitos
from customers.domain.models import (
    ConsentimentoEntrada,
    Endereco,
    Finalidade,
    NovoCliente,
    RgEntrada,
)
from shared.errors import ErroValidacao

HOJE = date(2026, 10, 18)


def novo(**kw: object) -> NovoCliente:
    base: dict[str, object] = {
        "id": "u1",
        "email": "m@example.com",
        "email_verificado": True,
        "nome_completo": "  Maria Souza Lima ",
        "cpf": "529.982.247-25",
        "data_nascimento": date(1990, 5, 12),
        "telefone": "+5511987654321",
        "endereco": Endereco("01310-100", "Av. Paulista", "1000", "Bela Vista", "Sao Paulo", "sp"),
        "consentimento": ConsentimentoEntrada("2026-10-v1", True, (Finalidade.EXECUCAO_CONTRATO,)),
        "rg": RgEntrada("12.345.678-9", "SSP", "sp"),
    }
    return NovoCliente(**{**base, **kw})  # type: ignore[arg-type]


@pytest.mark.parametrize("cpf", ["529.982.247-25", "52998224725", "111.444.777-35"])
def test_cpf_valido(cpf: str) -> None:
    assert cpf_valido(cpf)


@pytest.mark.parametrize("cpf", ["529.982.247-24", "111.111.111-11", "123", "", "abcdefghijk"])
def test_cpf_invalido(cpf: str) -> None:
    assert not cpf_valido(cpf)


def test_normaliza_dados() -> None:
    n = regras.validar_e_normalizar(novo(), HOJE, "2026-10-v1")
    assert n.nome_completo == "Maria Souza Lima"
    assert n.cpf == "52998224725"
    assert n.endereco.cep == "01310100"
    assert n.endereco.uf == "SP"
    assert n.rg is not None
    assert n.rg.uf == "SP"
    assert somente_digitos("a1b2") == "12"


def campos(**kw: object) -> list[str]:
    with pytest.raises(ErroValidacao) as exc:
        regras.validar_e_normalizar(novo(**kw), HOJE, "2026-10-v1")
    return [e["campo"] for e in exc.value.extras["erros"]]


def test_erros_de_campo() -> None:
    assert "cpf" in campos(cpf="529.982.247-24")
    assert "dataNascimento" in campos(data_nascimento=date(2030, 1, 1))
    assert "dataNascimento" in campos(data_nascimento=date(1800, 1, 1))
    assert "telefone" in campos(telefone="11987654321")
    assert "nomeCompleto" in campos(nome_completo="ab")
    assert "endereco.cep" in campos(endereco=Endereco("123", "r", "1", "b", "c", "SP"))
    assert "endereco.uf" in campos(endereco=Endereco("01310100", "r", "1", "b", "c", "XX"))
    assert "rg.uf" in campos(rg=RgEntrada("12.345.678-9", "SSP", "ZZ"))
    assert "rg.numero" in campos(rg=RgEntrada("1", "SSP", "SP"))


def test_menor_de_idade() -> None:
    assert campos(data_nascimento=date(2008, 10, 19)) == ["dataNascimento"]
    regras.validar_e_normalizar(novo(data_nascimento=date(2008, 10, 18)), HOJE, "2026-10-v1")


def test_consentimento() -> None:
    recusado = ConsentimentoEntrada("2026-10-v1", False, (Finalidade.EXECUCAO_CONTRATO,))
    assert "consentimento.aceito" in campos(consentimento=recusado)
    antigo = ConsentimentoEntrada("2025-01-v1", True, (Finalidade.EXECUCAO_CONTRATO,))
    assert "consentimento.versaoTermo" in campos(consentimento=antigo)
    so_marketing = ConsentimentoEntrada("2026-10-v1", True, (Finalidade.MARKETING,))
    assert "consentimento.finalidades" in campos(consentimento=so_marketing)


def test_mascara_rg_e_pendentes() -> None:
    assert regras.mascarar_rg("12.345.678-9") == "**.***.678-9"
    assert regras.campos_pendentes(
        rg=None, email_verificado=False, consentimento_vigente=False
    ) == (
        "rg",
        "email",
        "consentimento",
    )
