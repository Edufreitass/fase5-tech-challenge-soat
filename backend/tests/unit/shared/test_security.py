import pytest

from shared.errors import AcessoNegado, NaoAutenticado
from shared.security import Papel, exigir_papel, identidade_dos_claims


def test_sem_claims_nao_autenticado() -> None:
    with pytest.raises(NaoAutenticado):
        identidade_dos_claims(None)


def test_id_token_rejeitado(claims_admin: dict[str, str]) -> None:
    with pytest.raises(NaoAutenticado):
        identidade_dos_claims({**claims_admin, "token_use": "id"})


def test_client_id_desconhecido(claims_admin: dict[str, str]) -> None:
    with pytest.raises(NaoAutenticado):
        identidade_dos_claims({**claims_admin, "client_id": "outro"})


def test_admin_herda_vendedor(claims_admin: dict[str, str]) -> None:
    identidade = identidade_dos_claims(claims_admin)
    exigir_papel(identidade, (Papel.ADMIN,))
    exigir_papel(identidade, (Papel.VENDEDOR, Papel.ADMIN))
    exigir_papel(identidade, (Papel.VENDEDOR,))


def test_vendedor_nao_acessa_admin(claims_vendedor: dict[str, str]) -> None:
    identidade = identidade_dos_claims(claims_vendedor)
    exigir_papel(identidade, (Papel.VENDEDOR,))
    with pytest.raises(AcessoNegado):
        exigir_papel(identidade, (Papel.ADMIN,))


def test_cliente_nao_acessa_rota_de_funcionario(claims_cliente: dict[str, str]) -> None:
    identidade = identidade_dos_claims(claims_cliente)
    exigir_papel(identidade, (Papel.CLIENTE,))
    with pytest.raises(AcessoNegado):
        exigir_papel(identidade, (Papel.VENDEDOR, Papel.ADMIN))


def test_grupo_de_funcionario_em_pool_de_cliente_nao_vale(claims_cliente: dict[str, str]) -> None:
    identidade = identidade_dos_claims({**claims_cliente, "cognito:groups": "[admin]"})
    with pytest.raises(AcessoNegado):
        exigir_papel(identidade, (Papel.ADMIN,))


def test_grupos_em_lista() -> None:
    claims = {
        "sub": "x",
        "token_use": "access",
        "client_id": "cid-func",
        "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_FUNC",
        "cognito:groups": ["admin", "vendedor"],
    }
    assert identidade_dos_claims(claims).grupos == {"admin", "vendedor"}
