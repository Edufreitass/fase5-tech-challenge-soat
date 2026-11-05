"""Adaptadores de criptografia por campo e HMAC.

`CifradorSealedBox` so conhece a chave PUBLICA; `DecifradorSealedBox`
(chave privada) e usado
exclusivamente pela fn-clientes-interno e pela fn-lgpd-worker."""

import hashlib
import hmac
from collections.abc import Callable

from shared import crypto as cripto


class CifradorSealedBox:
    def __init__(self, chave_publica_b64: str, versao: int) -> None:
        self._chave = chave_publica_b64
        self._versao = versao

    def na_versao_atual(self, cifrado: str) -> bool:
        return cripto.versao_do_cifrado(cifrado) == self._versao

    def cifrar(self, valor: str, *, cliente_id: str, campo: str) -> str:
        return cripto.cifrar(
            valor,
            chave_publica_b64=self._chave,
            versao=self._versao,
            cliente_id=cliente_id,
            campo=campo,
        )


class DecifradorSealedBox:
    def __init__(self, chave_privada_por_versao: Callable[[int], str]) -> None:
        self._chave = chave_privada_por_versao

    def decifrar(self, cifrado: str, *, cliente_id: str, campo: str) -> str:
        versao = cripto.versao_do_cifrado(cifrado)
        return cripto.decifrar(
            cifrado, chave_privada_b64=self._chave(versao), cliente_id=cliente_id, campo=campo
        )


class HasherHmac:
    """HMAC-SHA256 com escopo (`cpf`, `email`, `ip`): unicidade e busca
    sem
    decifrar.
    """

    def __init__(self, segredo: str) -> None:
        self._segredo = segredo.encode()

    def hmac(self, escopo: str, valor: str) -> str:
        return hmac.new(self._segredo, f"{escopo}:{valor}".encode(), hashlib.sha256).hexdigest()
