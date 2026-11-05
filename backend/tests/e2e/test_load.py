"""Carga medida no ambiente dev: GET /veiculos p95 < 300 ms e POST
/vendas
p95 < 800 ms (sem cold start).

A meta e avaliada pela latencia do API Gateway (CloudWatch, p95 da
janela) - nao inclui a rede do
executor. O Locust (cliente) e registrado como evidencia
complementar.
"""

import csv
import json
import math
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from tests.e2e.conftest import Ambiente, salvar

META_LEITURA_MS = 300
META_COMPRA_MS = 800
# Cota de concorrencia do Lambda na conta Free plan = 10; cada compra
# usa 2 execucoes (vendas-api
# + clientes-interno).
CONCORRENCIA_COMPRA = 4


def p95_do_api_gateway(amb: Ambiente, inicio: datetime, fim: datetime) -> float:
    api = amb.api_url.split("//")[1].split(".")[0]
    nome = next(
        a["name"]
        for a in amb.sessao.client("apigateway").get_rest_apis(limit=50)["items"]
        if a["id"] == api
    )
    periodo = max(60, math.ceil((fim - inicio).total_seconds() / 60) * 60)
    for _ in range(12):  # as metricas do CloudWatch chegam com atraso de ~1-2 min
        r = amb.sessao.client("cloudwatch").get_metric_data(
            MetricDataQueries=[
                {
                    "Id": "lat",
                    "ReturnData": True,
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/ApiGateway",
                            "MetricName": "Latency",
                            "Dimensions": [
                                {"Name": "ApiName", "Value": nome},
                                {"Name": "Stage", "Value": "v1"},
                            ],
                        },
                        "Period": periodo,
                        "Stat": "p95",
                    },
                }
            ],
            StartTime=inicio,
            EndTime=fim + timedelta(seconds=periodo),
        )
        valores = r["MetricDataResults"][0]["Values"]
        if valores:
            return float(max(valores))
        time.sleep(15)
    raise AssertionError("sem metricas de Latency no CloudWatch para a janela")


def rodar_locust(
    amb: Ambiente,
    compradores: list[dict[str, str]],
    classe: str,
    usuarios: int,
    duracao: str,
    nome: str,
) -> dict[str, float]:
    saida = Path("build/evidencias")
    saida.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "API_URL": amb.api_url,
        "USUARIOS": json.dumps(compradores),
        "LIMITE_COMPRAS": "60",
    }
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "locust",
            "-f",
            "backend/tests/load/locustfile.py",
            "--headless",
            "--host",
            amb.api_url,
            "-u",
            str(usuarios),
            "-r",
            str(usuarios),
            "-t",
            duracao,
            "--csv",
            str(saida / nome),
            "--only-summary",
            classe,
        ],
        check=True,
        env=env,
        timeout=600,
    )
    with open(saida / f"{nome}_stats.csv", encoding="utf-8") as f:
        return {linha["Name"]: float(linha["95%"]) for linha in csv.DictReader(f)}


def aquecer(amb: Ambiente, compradores: list[dict[str, str]]) -> None:
    import httpx

    for _ in range(15):  # evita cold start na janela medida
        httpx.get(f"{amb.api_url}/veiculos?limit=5", timeout=30)
        httpx.get(
            f"{amb.api_url}/clientes/meu-perfil",
            headers={"Authorization": f"Bearer {compradores[0]['token']}"},
            timeout=30,
        )


def aquecer_compra(amb: Ambiente, compradores: list[dict[str, str]]) -> None:
    """Sem provisioned concurrency, a meta vale 'sem cold start':
    compras simultaneas aquecem
    as instancias de vendas-api e clientes-interno; depois espera-se a
    compensacao da saga."""
    import httpx

    veiculos = httpx.get(f"{amb.api_url}/veiculos?limit=20", timeout=30).json()["itens"]

    def comprar_e_desistir(indice: int) -> None:
        cab = {"Authorization": f"Bearer {compradores[indice]['token']}"}
        r = httpx.post(
            f"{amb.api_url}/vendas",
            json={"veiculoId": veiculos[indice]["id"]},
            headers=cab,
            timeout=60,
        )
        if r.status_code == 201:
            httpx.post(
                f"{amb.api_url}/vendas/{r.json()['id']}/desistencia", headers=cab, timeout=60
            )

    with ThreadPoolExecutor(max_workers=CONCORRENCIA_COMPRA) as pool:
        list(pool.map(comprar_e_desistir, range(CONCORRENCIA_COMPRA)))
    time.sleep(25)  # compensacoes da saga liberam veiculos e reservas


@pytest.mark.e2e
def test_meta_de_leitura_get_veiculos(
    ambiente: Ambiente, compradores: list[dict[str, str]]
) -> None:
    aquecer(ambiente, compradores)
    inicio = datetime.now(UTC)
    cliente_p95 = rodar_locust(ambiente, compradores, "Leitor", 10, "3m", "leitura")
    fim = datetime.now(UTC)
    servidor = p95_do_api_gateway(ambiente, inicio, fim)
    salvar(
        "carga_leitura.json",
        {
            "janela": [inicio.isoformat(), fim.isoformat()],
            "p95_api_gateway_ms": servidor,
            "p95_locust_ms": cliente_p95,
            "meta_ms": META_LEITURA_MS,
        },
    )
    assert servidor < META_LEITURA_MS, f"p95 de leitura {servidor} ms >= {META_LEITURA_MS} ms"


@pytest.mark.e2e
def test_meta_de_compra_post_vendas(ambiente: Ambiente, compradores: list[dict[str, str]]) -> None:
    aquecer_compra(ambiente, compradores)
    inicio = datetime.now(UTC)
    cliente_p95 = rodar_locust(
        ambiente, compradores, "Comprador", CONCORRENCIA_COMPRA, "4m", "compra"
    )
    fim = datetime.now(UTC)
    servidor = p95_do_api_gateway(ambiente, inicio, fim)
    salvar(
        "carga_compra.json",
        {
            "janela": [inicio.isoformat(), fim.isoformat()],
            "p95_api_gateway_ms": servidor,
            "p95_locust_ms": cliente_p95,
            "meta_ms": META_COMPRA_MS,
        },
    )
    assert servidor < META_COMPRA_MS, f"p95 de POST /vendas {servidor} ms >= {META_COMPRA_MS} ms"
