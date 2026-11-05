"""Direitos do titular e retencao: exportacao,
exclusao/anonimizacao, retencao e recifragem."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from customers.domain.models import Cliente, RetencaoLegal, SolicitacaoLgpd, StatusCliente
from customers.domain.ports import Hasher, IdentidadeRemocao, RepositorioClientes, VendasDoCliente
from shared.contracts import DadosTitular
from shared.errors import LimiteExcedido, PerfilClienteInexistente, ReservaAtivaExistente
from shared.ids import novo_id
from shared.time import agora_iso

JANELA_EXPORTACAO = timedelta(hours=24)
RETENCAO_LEGAL = timedelta(days=5 * 365 + 1)  # 5 anos apos a ultima venda
INATIVIDADE_PADRAO_DIAS = 730


def _parse(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


class ExportadorDados(Protocol):
    def exportar_dados(self, cliente_id: str) -> DadosTitular:
        """Dados pessoais decifrados (via fn-clientes-interno)."""
        ...


@dataclass
class ExportarDados:
    repositorio: RepositorioClientes
    vendas: VendasDoCliente
    exportador: ExportadorDados
    relogio: Callable[[], str] = field(default=agora_iso)
    gerar_id: Callable[[], str] = field(default=novo_id)

    def executar(self, cliente_id: str) -> dict[str, Any]:
        if self.repositorio.status_do_perfil(cliente_id) != StatusCliente.ATIVO.value:
            raise PerfilClienteInexistente("Faca o cadastro em POST /clientes.")
        agora = self.relogio()
        ultima = self.repositorio.ultima_exportacao(cliente_id)
        if ultima and _parse(agora) - _parse(ultima) < JANELA_EXPORTACAO:
            self.repositorio.registrar_solicitacao(
                SolicitacaoLgpd(
                    self.gerar_id(), cliente_id, "EXPORTACAO", "REJEITADA", agora, "LIMITE_DIARIO"
                )
            )
            raise LimiteExcedido("Uma exportacao por 24 horas.")
        dados = self.exportador.exportar_dados(cliente_id)
        resultado = {
            "geradoEm": agora,
            "titular": dados,
            "consentimentos": self.repositorio.consentimentos(cliente_id),
            "vendas": self.vendas.todas(cliente_id),
        }
        self.repositorio.registrar_solicitacao(
            SolicitacaoLgpd(self.gerar_id(), cliente_id, "EXPORTACAO", "CONCLUIDA", agora)
        )
        return resultado


@dataclass
class AnonimizarCliente:
    """Nucleo compartilhado pela exclusao pedida pelo titular e pela
    retencao automatica."""

    repositorio: RepositorioClientes
    vendas: VendasDoCliente
    hasher: Hasher
    identidade: IdentidadeRemocao
    relogio: Callable[[], str] = field(default=agora_iso)
    gerar_id: Callable[[], str] = field(default=novo_id)

    def executar(self, cliente: Cliente) -> None:
        agora = self.relogio()
        concluidas = self.vendas.concluidas(cliente.id)
        retencao = None
        if concluidas:
            ultima = max(_parse(data) for _, data in concluidas)
            retencao = RetencaoLegal(
                cliente.id,
                cliente.nome_completo,
                cliente.cpf_cifrado,
                tuple(i for i, _ in concluidas),
                int((ultima + RETENCAO_LEGAL).timestamp()),
            )
        self.repositorio.anonimizar(
            cliente,
            email_hmac=self.hasher.hmac("email", cliente.email.lower()),
            retencao=retencao,
            solicitacao=SolicitacaoLgpd(
                self.gerar_id(), cliente.id, "EXCLUSAO", "CONCLUIDA", agora
            ),
            agora=agora,
        )
        self.identidade.remover(cliente.id)


@dataclass
class ExcluirCliente:
    repositorio: RepositorioClientes
    vendas: VendasDoCliente
    anonimizar: AnonimizarCliente
    relogio: Callable[[], str] = field(default=agora_iso)
    gerar_id: Callable[[], str] = field(default=novo_id)

    def executar(self, cliente_id: str) -> None:
        status = self.repositorio.status_do_perfil(cliente_id)
        if status is None:
            raise PerfilClienteInexistente("Faca o cadastro em POST /clientes.")
        if status == StatusCliente.ANONIMIZADO.value:
            self.anonimizar.identidade.remover(
                cliente_id
            )  # repeticao: so garante a remocao do login
            return
        if self.vendas.em_andamento(cliente_id):
            self.repositorio.registrar_solicitacao(
                SolicitacaoLgpd(
                    self.gerar_id(),
                    cliente_id,
                    "EXCLUSAO",
                    "REJEITADA",
                    self.relogio(),
                    "VENDA_EM_ANDAMENTO",
                )
            )
            raise ReservaAtivaExistente(
                "Ha compra em andamento; conclua ou desista antes de excluir os dados."
            )
        cliente = self.repositorio.obter(cliente_id)
        if cliente is None:
            raise PerfilClienteInexistente("Faca o cadastro em POST /clientes.")
        self.anonimizar.executar(cliente)


@dataclass
class ExecutarRetencao:
    """Anonimiza clientes sem compra e inativos ha mais de N dias
    (padrao 730).
    """

    repositorio: RepositorioClientes
    vendas: VendasDoCliente
    anonimizar: AnonimizarCliente
    dias_inatividade: int = INATIVIDADE_PADRAO_DIAS
    agora: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))

    def executar(self) -> dict[str, int]:
        limite = (
            (self.agora() - timedelta(days=self.dias_inatividade))
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        anonimizados = ignorados = 0
        for cliente in self.repositorio.inativos_desde(limite):
            if self.vendas.todas(cliente.id):  # quem comprou segue a regra de retencao legal
                ignorados += 1
                continue
            self.anonimizar.executar(cliente)
            anonimizados += 1
        return {"anonimizados": anonimizados, "comCompra": ignorados}
