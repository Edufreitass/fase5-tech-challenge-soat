"""Assinatura do webhook do gateway: ``X-Gateway-Signature:
t=<epoch>,v1=<hex HMAC-SHA256>``.

O HMAC cobre ``"<t>.<corpo>"``. A verificacao e em tempo
constante e rejeita
timestamps fora da janela (anti-replay)."""

import hashlib
import hmac
import re

JANELA_SEGUNDOS = 300
_FORMATO = re.compile(r"^t=(\d+),v1=([0-9a-f]{64})$")


def assinar(segredo: str, epoch: int, corpo: str) -> str:
    mac = hmac.new(segredo.encode(), f"{epoch}.{corpo}".encode(), hashlib.sha256).hexdigest()
    return f"t={epoch},v1={mac}"


def verificar(cabecalho: str | None, corpo: str, segredos: list[str], agora: int) -> bool:
    """True se a assinatura confere com algum dos segredos
    (atual/anterior)
    e esta na janela.
    """
    if not cabecalho:
        return False
    casado = _FORMATO.match(cabecalho.strip())
    if not casado:
        return False
    epoch = int(casado.group(1))
    if abs(agora - epoch) > JANELA_SEGUNDOS:
        return False
    return any(
        hmac.compare_digest(assinar(segredo, epoch, corpo), cabecalho.strip())
        for segredo in segredos
    )
