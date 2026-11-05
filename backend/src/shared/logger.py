"""Logger estruturado (Powertools) com filtro que remove dados
pessoais.
"""

import logging
import os

from aws_lambda_powertools import Logger

from shared.masking import sanitizar, sanitizar_texto

_PADRAO_LOGRECORD = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys()) | {
    "message",
    "asctime",
    "taskName",
}


class FiltroPii(logging.Filter):
    """Mascara campos sensiveis em `extra` e padroes de CPF/e-mail na
    mensagem.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = sanitizar_texto(record.getMessage())
        record.args = None
        for chave in list(record.__dict__):
            if chave not in _PADRAO_LOGRECORD:
                record.__dict__[chave] = sanitizar({chave: record.__dict__[chave]})[chave]
        return True


def criar_logger(servico: str) -> Logger:
    logger = Logger(service=servico, level=os.environ.get("LOG_LEVEL", "INFO"))
    logger.addFilter(FiltroPii())
    return logger


def _instalar_fabrica_global() -> None:
    """Sanitiza o texto de TODO registro de log (inclusive de
    bibliotecas,
    como o DEBUG do
    Powertools que imprime os argumentos da rota), alem do filtro do
    logger da aplicacao.
    """
    original = logging.getLogRecordFactory()
    if getattr(original, "_revenda_pii", False):
        return

    def fabrica(*args: object, **kwargs: object) -> logging.LogRecord:
        registro = original(*args, **kwargs)
        registro.msg = sanitizar_texto(registro.getMessage())
        registro.args = None
        return registro

    fabrica._revenda_pii = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(fabrica)


_instalar_fabrica_global()
