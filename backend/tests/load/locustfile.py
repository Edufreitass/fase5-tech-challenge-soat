"""Carga (Locust): leitura publica e inicio de compra.

Variaveis: API_URL (com /v1), USUARIOS (JSON com tokens dos
compradores,
preparado por backend/tests/e2e),
LIMITE_COMPRAS (total de POST /vendas na execucao; limita as
transicoes
do Step Functions - free tier).
Passe a classe (`Leitor` ou `Comprador`) na linha de comando para
medir
cada meta separadamente.
"""

import json
import os
import random
import threading

from locust import HttpUser, between, constant, tag, task

LIMITE_COMPRAS = int(os.environ.get("LIMITE_COMPRAS", "60"))
USUARIOS = json.loads(os.environ.get("USUARIOS", "[]"))
_contador = {"compras": 0, "proximo": 0}
_trava = threading.Lock()


class Leitor(HttpUser):
    """Visitante anonimo navegando pelo catalogo."""

    weight = 8
    wait_time = between(0.5, 1.5)
    ids: list[str]

    def on_start(self) -> None:
        with self.client.get("/veiculos?limit=20", name="GET /veiculos", catch_response=True) as r:
            self.ids = [i["id"] for i in r.json().get("itens", [])] if r.status_code == 200 else []

    @tag("leitura")
    @task(6)
    def listar(self) -> None:
        self.client.get("/veiculos?limit=20", name="GET /veiculos")

    @tag("leitura")
    @task(2)
    def listar_filtrado(self) -> None:
        self.client.get(
            "/veiculos?limit=10&precoMin=40000.00&precoMax=90000.00",
            name="GET /veiculos (filtros)",
        )

    @tag("leitura")
    @task(2)
    def detalhe(self) -> None:
        if self.ids:
            self.client.get(f"/veiculos/{random.choice(self.ids)}", name="GET /veiculos/{id}")  # noqa: S311


class Comprador(HttpUser):
    """Cliente autenticado iniciando e desistindo da compra (libera o
    veiculo e a reserva)."""

    weight = 2
    wait_time = constant(
        10
    )  # a compensacao da saga leva alguns segundos; evita 409 de reserva ativa
    token: str
    ids: list[str]

    def on_start(self) -> None:
        with _trava:
            usuario = USUARIOS[_contador["proximo"] % len(USUARIOS)]
            _contador["proximo"] += 1
        self.token = usuario["token"]
        self.client.headers.update({"Authorization": f"Bearer {self.token}"})
        with self.client.get("/veiculos?limit=20", name="GET /veiculos", catch_response=True) as r:
            self.ids = [i["id"] for i in r.json().get("itens", [])] if r.status_code == 200 else []

    @tag("compra")
    @task
    def comprar_e_desistir(self) -> None:
        with _trava:
            if _contador["compras"] >= LIMITE_COMPRAS:
                self.environment.runner.quit()
                return
            _contador["compras"] += 1
        if not self.ids:
            return
        veiculo = random.choice(self.ids)  # noqa: S311
        with self.client.post(
            "/vendas", json={"veiculoId": veiculo}, name="POST /vendas", catch_response=True
        ) as r:
            if r.status_code == 201:
                r.success()
                venda_id = r.json()["id"]
                self.client.post(
                    f"/vendas/{venda_id}/desistencia", name="POST /vendas/{id}/desistencia"
                )
            elif r.status_code == 409:
                r.success()  # conflito legitimo (reserva ativa): resposta correta do negocio
            else:
                r.failure(f"status {r.status_code}")
