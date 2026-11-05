"""Criptografia hibrida por campo (libsodium sealed box, X25519 +
XSalsa20-Poly1305).

Formato: ``k<versao>:<base64url>``. O texto claro cifrado e um JSON
``{"v": valor, "clienteId": ..., "campo": ...}``; o contexto e
conferido
ao decifrar.
"""

import base64
import json

from nacl.public import PrivateKey, PublicKey, SealedBox

from shared.errors import ErroDecifragem

__all__ = ["ErroDecifragem", "cifrar", "decifrar", "gerar_par_chaves", "versao_do_cifrado"]


def gerar_par_chaves() -> tuple[str, str]:
    """Retorna (chave_privada_b64, chave_publica_b64)."""
    privada = PrivateKey.generate()
    return (
        base64.b64encode(bytes(privada)).decode(),
        base64.b64encode(bytes(privada.public_key)).decode(),
    )


def cifrar(valor: str, *, chave_publica_b64: str, versao: int, cliente_id: str, campo: str) -> str:
    caixa = SealedBox(PublicKey(base64.b64decode(chave_publica_b64)))
    texto = json.dumps({"v": valor, "clienteId": cliente_id, "campo": campo}, ensure_ascii=False)
    cifrado = caixa.encrypt(texto.encode())
    return f"k{versao}:{base64.urlsafe_b64encode(cifrado).decode()}"


def versao_do_cifrado(cifrado: str) -> int:
    prefixo, _, _ = cifrado.partition(":")
    if not prefixo.startswith("k") or not prefixo[1:].isdigit():
        raise ErroDecifragem("formato invalido")
    return int(prefixo[1:])


def decifrar(cifrado: str, *, chave_privada_b64: str, cliente_id: str, campo: str) -> str:
    _, _, corpo = cifrado.partition(":")
    try:
        caixa = SealedBox(PrivateKey(base64.b64decode(chave_privada_b64)))
        texto = json.loads(caixa.decrypt(base64.urlsafe_b64decode(corpo)))
    except Exception as erro:
        raise ErroDecifragem("falha ao decifrar") from erro
    if texto.get("clienteId") != cliente_id or texto.get("campo") != campo:
        raise ErroDecifragem("contexto divergente")
    return str(texto["v"])
