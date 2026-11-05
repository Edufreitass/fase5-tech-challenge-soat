"""Regras da venda independentes de AWS, HTTP e persistencia."""

from dataclasses import replace

import pytest

from sales.domain.models import StatusVenda, Venda
from shared.errors import EstadoInvalido

PERMITIDAS = {
    (StatusVenda.CRIADO, StatusVenda.RESERVADO),
    (StatusVenda.CRIADO, StatusVenda.CANCELADO),
    (StatusVenda.RESERVADO, StatusVenda.AGUARDANDO_PAGAMENTO),
    (StatusVenda.RESERVADO, StatusVenda.CANCELADO),
    (StatusVenda.AGUARDANDO_PAGAMENTO, StatusVenda.PAGO),
    (StatusVenda.AGUARDANDO_PAGAMENTO, StatusVenda.CANCELADO),
    (StatusVenda.PAGO, StatusVenda.CONCLUIDO),
    (StatusVenda.PAGO, StatusVenda.ESTORNADO),
}


@pytest.mark.parametrize("de", list(StatusVenda))
@pytest.mark.parametrize("para", list(StatusVenda))
def test_transicoes_e_repeticoes_respeitam_o_ciclo_da_venda(
    de: StatusVenda, para: StatusVenda
) -> None:
    venda = Venda("v", "c", "a", {}, 100, de, 1, "t", "t", "corr")
    repetida = replace(venda, status=para)
    if (de, para) in PERMITIDAS:
        venda.validar_transicao(de, para)
        repetida.validar_transicao(de, para)
    else:
        with pytest.raises(EstadoInvalido):
            venda.validar_transicao(de, para)
        with pytest.raises(EstadoInvalido):
            repetida.validar_transicao(de, para)


def test_transicao_recusa_estado_de_origem_desatualizado() -> None:
    venda = Venda("v", "c", "a", {}, 100, StatusVenda.PAGO, 1, "t", "t", "corr")
    with pytest.raises(EstadoInvalido):
        venda.validar_transicao(StatusVenda.CRIADO, StatusVenda.RESERVADO)
