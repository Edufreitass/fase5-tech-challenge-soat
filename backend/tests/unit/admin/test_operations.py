"""Operacoes /administracao: auditoria, solicitacoes LGPD,
sagas/redrive e rotacoes de segredo e chave PII."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import pytest
from moto import mock_aws

from admin.adapters.api import handler as modulo
from admin.adapters.aws.operations import AuditoriaCloudWatch, SegredosSsm
from admin.application.operations import AdministrarSagas, ConsultarAuditoria
from admin.domain.operations import FiltroAuditoria
from shared import parameters as parametros
from shared.errors import (
    ErroValidacao,
    RecursoNaoEncontrado,
    RequisicaoInvalida,
    SagaNaoReprocessavel,
)


class EventosFake:
    def __init__(self) -> None:
        self.publicados: list[tuple[str, dict[str, Any]]] = []

    def publicar(self, tipo: str, dados: dict[str, Any]) -> None:
        self.publicados.append((tipo, dados))


class SagasFake:
    def __init__(self, status: str | None) -> None:
        self.status = status
        self.reprocessadas: list[str] = []

    def listar(
        self, status: str, *, limite: int, proximo: str | None
    ) -> tuple[list[dict[str, Any]], None]:
        return [{"vendaId": "v1", "status": status}], None

    def status_da_execucao(self, venda_id: str) -> str | None:
        return self.status

    def reprocessar(self, venda_id: str) -> None:
        self.reprocessadas.append(venda_id)


def test_redrive_so_para_execucoes_com_falha() -> None:
    eventos = EventosFake()
    for status in ("RUNNING", "SUCCEEDED"):
        with pytest.raises(SagaNaoReprocessavel):
            AdministrarSagas(SagasFake(status), eventos).reprocessar("adm", "v1")
    with pytest.raises(RecursoNaoEncontrado):
        AdministrarSagas(SagasFake(None), eventos).reprocessar("adm", "v1")
    for status in ("FAILED", "TIMED_OUT", "ABORTED"):
        fake = SagasFake(status)
        AdministrarSagas(fake, eventos).reprocessar("adm", "v1")
        assert fake.reprocessadas == ["v1"]
    assert [t for t, _ in eventos.publicados] == [
        "AcaoAdministrativa"
    ] * 3  # so as acoes efetivadas sao auditadas


def test_listar_sagas_valida_status() -> None:
    with pytest.raises(ErroValidacao):
        AdministrarSagas(SagasFake("FAILED"), EventosFake()).listar("adm", "SUCCEEDED", 10, None)


def test_janela_da_auditoria_limitada_a_31_dias_e_valores_em_allowlist() -> None:
    class Trilha:
        def buscar(
            self, filtro: FiltroAuditoria, *, limite: int, proximo: str | None
        ) -> tuple[list[dict[str, Any]], None]:
            return [{"ok": True}], None

    caso = ConsultarAuditoria(Trilha(), EventosFake())
    agora = datetime.now(UTC)
    with pytest.raises(ErroValidacao):
        caso.executar("a", None, None, None, agora - timedelta(days=32), agora, 10, None)
    with pytest.raises(ErroValidacao):
        caso.executar("a", None, None, None, agora, agora - timedelta(days=1), 10, None)
    for valor in ('x" || $.a = "y', "a b", "a;b", "{x}"):
        with pytest.raises(RequisicaoInvalida):
            caso.executar("a", valor, None, None, None, None, 10, None)
    assert caso.executar(
        "a", "cli-1", "adm-1", "CRIAR_FUNCIONARIO", agora - timedelta(days=30), agora, 10, None
    )[0] == [{"ok": True}]


def test_filter_pattern_montado_so_com_valores_validados() -> None:
    f = FiltroAuditoria(
        "cli-1", "adm-1", "AcaoAdministrativa", datetime.now(UTC), datetime.now(UTC)
    )
    padrao = AuditoriaCloudWatch.padrao(f)
    assert padrao == (
        '{ ($.clienteId = "cli-1" || $.recurso = "cli-1") && $.atorId'
        ' = "adm-1" && ($.tipo = "AcaoAdministrativa" || $.acao = "Ac'
        'aoAdministrativa") }'
    )
    assert (
        AuditoriaCloudWatch.padrao(
            FiltroAuditoria(None, None, None, datetime.now(UTC), datetime.now(UTC))
        )
        == ""
    )


@pytest.fixture
def aws() -> Iterator[None]:
    with mock_aws():
        boto3.client("ssm").put_parameter(
            Name="/revenda/dev/pii/versao-atual", Value="1", Type="String"
        )
        yield


class LambdaFake:
    def __init__(self) -> None:
        self.chamadas: list[dict[str, Any]] = []

    def invoke(self, **kwargs: Any) -> None:
        self.chamadas.append(kwargs)


def test_rotacao_do_segredo_do_webhook_versiona_e_nao_le_o_segredo(aws: None) -> None:
    ssm = boto3.client("ssm")
    ssm.put_parameter(
        Name="/revenda/dev/segredos/webhook-hmac-atual", Value="antigo", Type="SecureString"
    )
    rot = SegredosSsm(ssm, LambdaFake(), "/revenda/dev", "fn-lgpd")
    assert rot.rotacionar_webhook() == 2
    novo = ssm.get_parameter(Name="/revenda/dev/segredos/webhook-hmac-atual", WithDecryption=True)[
        "Parameter"
    ]["Value"]
    anterior = ssm.get_parameter(
        Name="/revenda/dev/segredos/webhook-hmac-atual:1", WithDecryption=True
    )["Parameter"]["Value"]
    assert novo != "antigo"
    assert anterior == "antigo"  # a versao anterior continua acessivel para o webhook


def test_rotacao_da_chave_pii_publica_a_nova_chave_e_dispara_a_recifragem(aws: None) -> None:
    ssm, lam = boto3.client("ssm"), LambdaFake()
    versao = SegredosSsm(ssm, lam, "/revenda/dev", "fn-lgpd").rotacionar_chave_pii()
    assert versao == 2
    assert ssm.get_parameter(Name="/revenda/dev/pii/versao-atual")["Parameter"]["Value"] == "2"
    assert ssm.get_parameter(Name="/revenda/dev/pii/chave-publica-v2")["Parameter"]["Value"]
    assert ssm.get_parameter(
        Name="/revenda/dev/segredos/pii-chave-privada-v2", WithDecryption=True
    )["Parameter"]["Value"]
    payload = json.loads(lam.chamadas[0]["Payload"])
    assert (lam.chamadas[0]["InvocationType"], payload) == (
        "Event",
        {"acao": "RECIFRAR", "versaoNova": 2, "versoesAntigas": [1]},
    )


def test_rotas_admin_no_handler(
    aws: None,
    claims_admin: dict[str, str],
    claims_vendedor: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ssm = boto3.client("ssm")
    ssm.put_parameter(
        Name="/revenda/dev/segredos/webhook-hmac-atual", Value="antigo", Type="SecureString"
    )
    ssm.put_parameter(Name="/revenda/dev/segredos/cursor-hmac", Value="c", Type="String")
    parametros.segredo_cursor.cache_clear()
    monkeypatch.setenv("LGPD_WORKER_FUNCAO", "fn-lgpd")
    monkeypatch.setattr(modulo, "_eventos", EventosFake)
    monkeypatch.setattr(
        modulo,
        "boto3",
        type(
            "B",
            (),
            {
                "client": staticmethod(
                    lambda nome, **_: LambdaFake() if nome == "lambda" else boto3.client(nome)
                )
            },
        ),
    )

    def chamar(metodo: str, caminho: str, claims: dict[str, str]) -> tuple[int, Any]:
        evento = {
            "httpMethod": metodo,
            "path": caminho,
            "resource": caminho,
            "headers": {},
            "multiValueHeaders": {},
            "queryStringParameters": None,
            "body": None,
            "isBase64Encoded": False,
            "requestContext": {"authorizer": {"claims": claims}, "requestId": "r", "stage": "v1"},
        }
        r = modulo.handler(evento, None)
        return r["statusCode"], json.loads(r["body"] or "{}")

    assert chamar("POST", "/administracao/segredos/webhook/rotacao", claims_vendedor)[0] == 403
    assert chamar("POST", "/administracao/segredos/webhook/rotacao", claims_admin) == (
        200,
        {"versao": 2},
    )
    assert chamar("POST", "/administracao/chaves-pii/rotacao", claims_admin) == (
        202,
        {"versao": 2},
    )
    assert chamar("GET", "/administracao/sagas", claims_admin)[0] != 403
