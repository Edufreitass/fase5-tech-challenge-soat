"""Rejeita formatos invalidos nas fronteiras do backend."""

import io
import json
from unittest.mock import Mock

import pytest

from customers.adapters.internal.customer import InvocadorClientesInterno
from shared.errors import DependenciaIndisponivel, RequisicaoInvalida
from shared.pagination import codificar, decodificar_cursor


@pytest.mark.parametrize("chave", [None, [], "token", {}, {"pk": 1}, {"pk": {"S": "v"}}])
def test_rejeita_cursor_assinado_com_estrutura_invalida(chave: object) -> None:
    # Arrange
    segredo = b"segredo-de-teste"
    token = codificar(chave, segredo)

    # Act / Assert
    with pytest.raises(RequisicaoInvalida, match="nextToken invalido"):
        decodificar_cursor(token, segredo)


def test_cursor_preserva_as_chaves_textuais() -> None:
    chave = {"pk": "VENDA#v1", "sk": "META", "gsi1pk": "CLIENTE#c1"}
    segredo = b"segredo-de-teste"

    resultado = decodificar_cursor(codificar(chave, segredo), segredo)

    assert resultado == chave


@pytest.mark.parametrize(
    "corpo",
    [{"valido": "sim", "camposPendentes": []}, {"valido": True}, [], None],
)
def test_rejeita_resposta_interna_fora_do_contrato(corpo: object) -> None:
    cliente_lambda = Mock()
    cliente_lambda.invoke.return_value = {"Payload": io.BytesIO(json.dumps(corpo).encode())}
    invocador = InvocadorClientesInterno(cliente_lambda, "clientes-interno")

    with pytest.raises(DependenciaIndisponivel, match="Resposta invalida"):
        invocador.validar_comprador("c1")


def test_resposta_valida_nao_converte_strings_em_booleanos() -> None:
    cliente_lambda = Mock()
    cliente_lambda.invoke.return_value = {
        "Payload": io.BytesIO(b'{"valido": true, "camposPendentes": ["rg"]}')
    }
    invocador = InvocadorClientesInterno(cliente_lambda, "clientes-interno")

    resposta = invocador.validar_comprador("c1")

    assert resposta == {"valido": True, "camposPendentes": ["rg"]}


def test_resposta_malformada_nao_expoe_dados_no_erro() -> None:
    cliente_lambda = Mock()
    cliente_lambda.invoke.return_value = {"Payload": io.BytesIO(b'{"cpf": "incompleto"')}
    invocador = InvocadorClientesInterno(cliente_lambda, "clientes-interno")

    with pytest.raises(DependenciaIndisponivel) as falha:
        invocador.obter_dados_cobranca("c1")

    assert "cpf" not in str(falha.value)
    assert falha.value.__suppress_context__
