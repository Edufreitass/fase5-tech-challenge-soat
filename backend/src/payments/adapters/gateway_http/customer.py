"""Cliente HTTPS do gateway de pagamento (mock) com SigV4, timeout de 5
s e
circuit breaker.
"""

import json
import time
from collections.abc import Callable
from typing import Any

import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials

from shared.errors import DependenciaIndisponivel

TIMEOUT_SEGUNDOS = 5.0
FALHAS_PARA_ABRIR = 5
JANELA_SEGUNDOS = 60.0
ABERTO_POR_SEGUNDOS = 30.0


class CircuitBreaker:
    """Em memoria da instancia: 5 falhas em 60 s abrem por 30 s."""

    def __init__(self, relogio: Callable[[], float] = time.monotonic) -> None:
        self._relogio = relogio
        self._falhas: list[float] = []
        self._aberto_ate = 0.0

    def permitir(self) -> bool:
        return self._relogio() >= self._aberto_ate

    def sucesso(self) -> None:
        self._falhas.clear()

    def falha(self) -> None:
        agora = self._relogio()
        self._falhas = [t for t in self._falhas if agora - t < JANELA_SEGUNDOS] + [agora]
        if len(self._falhas) >= FALHAS_PARA_ABRIR:
            self._aberto_ate = agora + ABERTO_POR_SEGUNDOS


class GatewayHttp:
    def __init__(
        self,
        base_url: str,
        credenciais: Credentials,
        regiao: str,
        http: httpx.Client | None = None,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._cred = credenciais
        self._regiao = regiao
        self._http = http or httpx.Client(timeout=TIMEOUT_SEGUNDOS)
        self._breaker = breaker or CircuitBreaker()

    def _chamar(self, caminho: str, corpo: dict[str, Any]) -> dict[str, Any]:
        if not self._breaker.permitir():
            raise DependenciaIndisponivel("Gateway de pagamento temporariamente indisponivel.")
        url = f"{self._base}{caminho}"
        dados = json.dumps(corpo)
        pedido = AWSRequest(
            method="POST", url=url, data=dados, headers={"Content-Type": "application/json"}
        )
        SigV4Auth(self._cred, "execute-api", self._regiao).add_auth(pedido)
        try:
            resposta = self._http.post(url, content=dados, headers=dict(pedido.headers.items()))
            resposta.raise_for_status()
        except httpx.HTTPError as erro:
            self._breaker.falha()
            raise DependenciaIndisponivel("Falha ao chamar o gateway de pagamento.") from erro
        self._breaker.sucesso()
        return resposta.json() if resposta.content else {}

    def criar_cobranca(
        self, *, referencia: str, valor_centavos: int, nome: str, cpf: str, expira_em: str
    ) -> tuple[str, str]:
        r = self._chamar(
            "/_simulacao/pagamentos/cobrancas",
            {
                "referencia": referencia,
                "valorCentavos": valor_centavos,
                "pagador": {"nome": nome, "cpf": cpf},
                "expiraEm": expira_em,
            },
        )
        return str(r["idTransacaoExterna"]), str(r["pixCopiaECola"])

    def cancelar_cobranca(self, id_transacao_externa: str) -> None:
        self._chamar(f"/_simulacao/pagamentos/cobrancas/{id_transacao_externa}/cancelar", {})

    def estornar(self, id_transacao_externa: str, valor_centavos: int) -> str:
        r = self._chamar(
            "/_simulacao/pagamentos/estornos",
            {"idTransacaoExterna": id_transacao_externa, "valorCentavos": valor_centavos},
        )
        return str(r["idEstornoExterno"])
