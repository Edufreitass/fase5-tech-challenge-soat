"""Geracao de identificadores UUID v7 (ordenaveis por tempo)."""

import os
import time
import uuid


def novo_id() -> str:
    """UUID v7 (RFC 9562): 48 bits de timestamp em ms + aleatorio."""
    milissegundos = time.time_ns() // 1_000_000
    aleatorio = int.from_bytes(os.urandom(10), "big")
    valor = (milissegundos & ((1 << 48) - 1)) << 80
    valor |= 0x7 << 76
    valor |= ((aleatorio >> 62) & 0xFFF) << 64
    valor |= 0b10 << 62
    valor |= aleatorio & ((1 << 62) - 1)
    return str(uuid.UUID(int=valor))
