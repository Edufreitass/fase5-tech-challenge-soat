import json
import logging
import uuid

import pytest

from shared import crypto as cripto
from shared import pagination as paginacao
from shared.errors import RequisicaoInvalida
from shared.ids import novo_id
from shared.logger import FiltroPii
from shared.masking import mascarar_cpf, sanitizar


def test_uuid7_valido_e_ordenavel() -> None:
    a, b = novo_id(), novo_id()
    assert uuid.UUID(a).version == 7
    assert a != b


def test_cripto_ida_e_volta_e_contexto() -> None:
    privada, publica = cripto.gerar_par_chaves()
    cifrado = cripto.cifrar(
        "12345678909", chave_publica_b64=publica, versao=1, cliente_id="c1", campo="cpf"
    )
    assert cifrado.startswith("k1:")
    assert "12345678909" not in cifrado
    assert cripto.versao_do_cifrado(cifrado) == 1
    assert cripto.decifrar(cifrado, chave_privada_b64=privada, cliente_id="c1", campo="cpf") == (
        "12345678909"
    )
    with pytest.raises(cripto.ErroDecifragem):
        cripto.decifrar(cifrado, chave_privada_b64=privada, cliente_id="c2", campo="cpf")
    with pytest.raises(cripto.ErroDecifragem):
        cripto.decifrar(cifrado, chave_privada_b64=privada, cliente_id="c1", campo="rg")
    with pytest.raises(cripto.ErroDecifragem):
        cripto.decifrar(
            cifrado, chave_privada_b64=cripto.gerar_par_chaves()[0], cliente_id="c1", campo="cpf"
        )
    with pytest.raises(cripto.ErroDecifragem):
        cripto.versao_do_cifrado("lixo")


def test_cursor_assinado() -> None:
    token = paginacao.codificar({"pk": "A"}, b"segredo")
    assert paginacao.decodificar(token, b"segredo") == {"pk": "A"}
    with pytest.raises(RequisicaoInvalida):
        paginacao.decodificar(token, b"outro")
    with pytest.raises(RequisicaoInvalida):
        paginacao.decodificar("%%%", b"segredo")


@pytest.mark.parametrize(("bruto", "esperado"), [(None, 20), ("1", 1), ("50", 50)])
def test_limite_valido(bruto: str | None, esperado: int) -> None:
    assert paginacao.validar_limite(bruto) == esperado


@pytest.mark.parametrize("bruto", ["0", "51", "x", "-1"])
def test_limite_invalido(bruto: str) -> None:
    with pytest.raises(RequisicaoInvalida):
        paginacao.validar_limite(bruto)


def test_sanitizar_chaves_e_padroes() -> None:
    saida = sanitizar(
        {
            "cpf": "123",
            "nested": {"Email": "a@b.com", "ok": "valor 529.982.247-25 fim"},
            "lista": ["x@y.org"],
            "n": 1,
        }
    )
    assert saida["cpf"] == "***"
    assert saida["nested"]["Email"] == "***"
    assert "529.982.247-25" not in json.dumps(saida)
    assert "x@y.org" not in json.dumps(saida)
    assert saida["n"] == 1
    assert mascarar_cpf("24725") == "***.***.247-25"


def test_filtro_do_logger_remove_pii(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("teste-pii")
    logger.addFilter(FiltroPii())
    with caplog.at_level(logging.INFO, logger="teste-pii"):
        logger.info("cliente 529.982.247-25 e a@b.com", extra={"cpf": "52998224725", "id": "1"})
    registro = caplog.records[0]
    assert "529.982.247-25" not in registro.getMessage()
    assert "a@b.com" not in registro.getMessage()
    assert registro.cpf == "***"  # type: ignore[attr-defined]
    assert registro.id == "1"  # type: ignore[attr-defined]
