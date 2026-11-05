"""Resolver HTTP comum: problem+json, correlationId, cabecalhos de
seguranca e papeis."""

import json
import re
from collections.abc import Callable
from typing import Any

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.exceptions import NotFoundError
from aws_lambda_powertools.event_handler.middlewares import NextMiddleware
from aws_lambda_powertools.event_handler.middlewares.openapi_validation import (
    OpenAPIRequestValidationMiddleware,
    OpenAPIResponseValidationMiddleware,
)
from aws_lambda_powertools.event_handler.openapi.exceptions import RequestValidationError
from aws_lambda_powertools.logging import correlation_paths
from botocore.exceptions import ClientError

from shared.errors import ErroNegocio, PrecondicaoObrigatoria, RequisicaoInvalida
from shared.ids import novo_id
from shared.logger import criar_logger
from shared.metrics import DYNAMODB_THROTTLING, emitir
from shared.security import Identidade, Papel, exigir_papel, identidade_dos_claims

CODIGOS_THROTTLING = frozenset(
    {"ProvisionedThroughputExceededException", "ThrottlingException", "RequestLimitExceeded"}
)
# Cota de concorrencia do Lambda (a conta Free plan tem 10): a chamada
# aninhada vendas ->
# clientes-interno
# esgota a cota antes do DynamoDB; a resposta correta e 503 com Retry-
# After, nao 500.
CODIGOS_COTA_LAMBDA = frozenset({"TooManyRequestsException"})
STATUS_ERRO = 400
_IF_MATCH = re.compile(r"v(\d+)")
PROBLEMA = "application/problem+json"
PREFIXO_TIPO = "urn:revenda:problema:"
CABECALHOS_SEGURANCA = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def problema(  # noqa: PLR0913, PLR0917
    status: int,
    slug: str,
    titulo: str,
    detalhe: str | None,
    instancia: str,
    correlation_id: str,
    **extras: Any,
) -> Response[str]:
    corpo: dict[str, Any] = {
        "type": f"{PREFIXO_TIPO}{slug}",
        "title": titulo,
        "status": status,
        "instance": instancia,
        "correlationId": correlation_id,
        **extras,
    }
    if detalhe:
        corpo["detail"] = detalhe
    return Response(status_code=status, content_type=PROBLEMA, body=json.dumps(corpo))


class _ValidacaoComAutorizacao(OpenAPIRequestValidationMiddleware):
    """O Powertools valida o corpo ANTES dos middlewares da rota;
    aqui o
    papel e conferido primeiro,
    para que 401/403 nunca virem 422 (e o contrato nao vaze para
    quem
    nao tem acesso).
    """

    def handler(self, app: Any, next_middleware: NextMiddleware) -> Response[Any]:
        for middleware in app.context["_route"].middlewares:
            autorizar = getattr(middleware, "autorizar", None)
            if autorizar is not None:
                autorizar()
        return super().handler(app, next_middleware)


class AppRevenda(APIGatewayRestResolver):
    """Resolver que exige declaracao de papel em toda rota."""

    def __init__(self, servico: str, **kwargs: Any) -> None:
        super().__init__(enable_validation=True, **kwargs)
        self.logger = criar_logger(servico)
        self._request_validation_middleware = _ValidacaoComAutorizacao()  # type: ignore[no-untyped-call]
        self._response_validation_middleware = OpenAPIResponseValidationMiddleware(
            validation_serializer=self._serializer,
            has_response_validation_error=self._has_response_validation_error,
        )
        self.rotas: list[tuple[str, str, tuple[Papel, ...]]] = []
        self.correlation_id = ""
        self.exception_handler(ErroNegocio)(self._tratar_negocio)
        self.exception_handler(RequestValidationError)(self._tratar_validacao)
        self.exception_handler(NotFoundError)(self._tratar_nao_encontrado)
        self.exception_handler(Exception)(self._tratar_inesperado)

    # -- declaracao de rotas
    # ---------------------------------------------------
    def rota(
        self, metodo: str, caminho: str, *papeis: Papel, **openapi: Any
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        publica = papeis in ((Papel.ANONIMO,), (Papel.SISTEMA,))
        if not papeis:
            raise ValueError("toda rota deve declarar ao menos um papel")

        def autorizar() -> None:
            if not publica:
                exigir_papel(self.identidade(), papeis)

        def exigir(app: Any, proximo: NextMiddleware) -> Response[Any]:
            autorizar()
            return proximo(app)

        exigir.autorizar = autorizar  # type: ignore[attr-defined]  # lido por _ValidacaoComAutorizacao

        def decorador(func: Callable[..., Any]) -> Callable[..., Any]:
            self.rotas.append((metodo.upper(), caminho, papeis))
            registrador = self.route(
                caminho, method=metodo.upper(), middlewares=[exigir], **openapi
            )
            return registrador(func)

        return decorador

    def versao_if_match(self) -> int:
        """`If-Match: "v3"` -> 3. Ausente = 428; formato invalido =
        400.
        """
        bruto = self.current_event.headers.get("If-Match")
        if not bruto:
            raise PrecondicaoObrigatoria("Envie o ETag do recurso no cabecalho If-Match.")
        casado = _IF_MATCH.fullmatch(bruto.strip().removeprefix("W/").strip('"'))
        if not casado:
            raise RequisicaoInvalida('If-Match deve ter o formato "v<numero>".')
        return int(casado.group(1))

    def identidade(self) -> Identidade:
        autorizador = self.current_event.request_context.authorizer
        claims = autorizador.claims if autorizador is not None else None
        return identidade_dos_claims(claims)

    # -- ciclo da requisicao e erros
    # -------------------------------------------
    def resolve(self, event: dict[str, Any], context: Any) -> dict[str, Any]:  # type: ignore[override]
        cabecalhos = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
        self.correlation_id = cabecalhos.get("x-correlation-id") or novo_id()
        self.logger.set_correlation_id(self.correlation_id)
        resposta: dict[str, Any] = super().resolve(event, context)
        extras = {"X-Correlation-Id": self.correlation_id, **CABECALHOS_SEGURANCA}
        autenticada = bool((event.get("requestContext") or {}).get("authorizer"))
        if autenticada or resposta["statusCode"] >= STATUS_ERRO:
            extras["Cache-Control"] = "no-store"
        multi: dict[str, list[str]] = resposta.setdefault("multiValueHeaders", {})
        presentes = {k.lower() for k in multi}
        for chave, valor in extras.items():
            if chave.lower() not in presentes:
                multi[chave] = [valor]
        return resposta

    def _instancia(self) -> str:
        return str(self.current_event.path)

    def _tratar_negocio(self, erro: ErroNegocio) -> Response[str]:
        return problema(
            erro.status,
            erro.slug,
            erro.titulo,
            erro.detalhe,
            self._instancia(),
            self.correlation_id,
            **erro.extras,
        )

    def _tratar_validacao(self, erro: RequestValidationError) -> Response[str]:
        erros = [
            {"campo": ".".join(str(p) for p in e.get("loc", ())), "mensagem": e.get("msg", "")}
            for e in erro.errors()
        ]
        return problema(
            422,
            "validacao",
            "Erro de validacao",
            None,
            self._instancia(),
            self.correlation_id,
            erros=erros,
        )

    def _tratar_nao_encontrado(self, _erro: NotFoundError) -> Response[str]:
        return problema(
            404,
            "recurso-nao-encontrado",
            "Recurso nao encontrado",
            None,
            self._instancia(),
            self.correlation_id,
        )

    def _tratar_inesperado(self, erro: Exception) -> Response[str]:
        codigo = (
            erro.response.get("Error", {}).get("Code") if isinstance(erro, ClientError) else None
        )
        if codigo in CODIGOS_THROTTLING | CODIGOS_COTA_LAMBDA:
            # throttling persistente apos os retries do SDK: pede nova
            # tentativa (o alarme de throttling so conta o
            # DynamoDB)
            if codigo in CODIGOS_THROTTLING:
                emitir(DYNAMODB_THROTTLING)
            self.logger.warning("throttling", extra={"codigo": codigo})
            resposta = problema(
                503,
                "dependencia-indisponivel",
                "Servico temporariamente sobrecarregado",
                None,
                self._instancia(),
                self.correlation_id,
            )
            resposta.headers["Retry-After"] = "2"
            return resposta
        self.logger.exception("erro nao tratado", extra={"tipoErro": type(erro).__name__})
        return problema(
            500, "erro-interno", "Erro interno", None, self._instancia(), self.correlation_id
        )


def processar(app: AppRevenda, evento: dict[str, Any], contexto: Any) -> dict[str, Any]:
    app.logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
    return app.resolve(evento, contexto)
