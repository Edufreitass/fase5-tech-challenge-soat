"""Casos de uso do cliente na compra: reservar, consultar e desistir."""

from collections.abc import Callable
from dataclasses import dataclass, field

from sales.domain.models import (
    Ator,
    DadosPagamento,
    EventoVenda,
    MotivoCancelamento,
    StatusVenda,
    Venda,
)
from sales.domain.ports import (
    ClientesInterno,
    InteracaoCompra,
    LeitorPagamento,
    LeituraVenda,
    ReservaVendas,
    Saga,
)
from shared.contracts import DocumentacaoRetirada
from shared.errors import (
    CadastroIncompleto,
    PerfilClienteInexistente,
    RecursoNaoEncontrado,
    ReservaAtivaExistente,
    VeiculoIndisponivel,
    VendaNaoCancelavel,
)
from shared.ids import novo_id
from shared.time import agora_iso, somar_segundos
from vehicles.domain.models import StatusVeiculo
from vehicles.domain.ports import RepositorioVeiculos


@dataclass
class IniciarCompra:
    vendas: ReservaVendas
    veiculos: RepositorioVeiculos
    clientes: ClientesInterno
    prazo_pagamento_segundos: int
    gerar_id: Callable[[], str] = field(default=novo_id)
    relogio: Callable[[], str] = field(default=agora_iso)

    def executar(self, cliente_id: str, veiculo_id: str, correlation_id: str) -> Venda:
        validacao = self.clientes.validar_comprador(cliente_id)
        if not validacao["valido"]:
            pendentes = list(validacao["camposPendentes"])
            if pendentes == ["cadastro"]:
                raise PerfilClienteInexistente("Faca o cadastro em POST /clientes.")
            raise CadastroIncompleto(camposPendentes=pendentes)

        veiculo = self.veiculos.obter(veiculo_id)
        if veiculo is None or veiculo.status == StatusVeiculo.INATIVO:
            raise RecursoNaoEncontrado("Veiculo nao encontrado.")
        if veiculo.status != StatusVeiculo.DISPONIVEL:
            raise VeiculoIndisponivel("O veiculo foi reservado por outro cliente.")

        agora = self.relogio()
        venda = Venda(
            id=self.gerar_id(),
            cliente_id=cliente_id,
            veiculo_id=veiculo.id,
            veiculo_snapshot={
                "id": veiculo.id,
                "marca": veiculo.marca,
                "modelo": veiculo.modelo,
                "anoModelo": veiculo.ano_modelo,
                "cor": veiculo.cor,
            },
            preco_negociado_centavos=veiculo.preco_centavos,
            status=StatusVenda.CRIADO,
            versao=1,
            criado_em=agora,
            atualizado_em=agora,
            correlation_id=correlation_id,
        )
        # Fase 1: a venda nasce CRIADO e so depois tenta a
        # reserva atomica.
        self.vendas.criar(venda, EventoVenda(StatusVenda.CRIADO, Ator.CLIENTE, agora))
        expira_em = somar_segundos(agora, self.prazo_pagamento_segundos)
        try:
            self.vendas.reservar(venda, veiculo.versao, expira_em, self.relogio())
        except (VeiculoIndisponivel, ReservaAtivaExistente) as erro:
            self.vendas.cancelar_por_conflito(venda.id, self.relogio())
            erro.extras["vendaId"] = venda.id
            raise
        reservada = self.vendas.obter(venda.id)
        assert reservada is not None  # noqa: S101
        return reservada


@dataclass
class ConsultarVenda:
    vendas: LeituraVenda
    pagamentos: LeitorPagamento

    def executar(
        self, venda_id: str, *, solicitante_id: str, funcionario: bool
    ) -> tuple[Venda, DadosPagamento | None, list[EventoVenda]]:
        venda = self.vendas.obter(venda_id)
        # Anti-IDOR: venda de outro cliente e indistinguivel de
        # inexistente.
        if venda is None or (not funcionario and venda.cliente_id != solicitante_id):
            raise RecursoNaoEncontrado("Venda nao encontrada.")
        pagamento = self.pagamentos.por_id(venda.pagamento_id) if venda.pagamento_id else None
        return venda, pagamento, self.vendas.historico(venda_id)


@dataclass
class DesistirDaCompra:
    vendas: InteracaoCompra
    saga: Saga

    def executar(self, venda_id: str, cliente_id: str) -> None:
        venda = self.vendas.obter(venda_id)
        if venda is None or venda.cliente_id != cliente_id:
            raise RecursoNaoEncontrado("Venda nao encontrada.")
        venda.validar_desistencia()
        # Persiste antes do callback. A retirada compete pela mesma
        # linha e precisa enxergar a desistencia imediatamente.
        if not self.vendas.solicitar_desistencia(venda_id):
            raise VendaNaoCancelavel("A venda mudou de estado; consulte e tente novamente.")
        venda = self._reler(venda_id)
        if venda.task_token:
            # Um token consumido nao desfaz a decisao. A proxima espera
            # consulta a flag e compensa. Erros transitorios
            # propagam para permitir nova tentativa do callback.
            self.saga.enviar_falha(venda.task_token, "Venda.Desistencia", "cliente desistiu")

    def _reler(self, venda_id: str) -> Venda:
        venda = self.vendas.obter(venda_id)
        if venda is None:
            raise RecursoNaoEncontrado("Venda nao encontrada.")
        return venda


@dataclass
class ConfirmarRetirada:
    """Retirada pelo vendedor: pivot da saga; depois dela a
    desistencia retorna 409."""

    vendas: InteracaoCompra
    saga: Saga

    def executar(
        self, venda_id: str, retirada_em: str, documentacao: DocumentacaoRetirada
    ) -> None:
        venda = self.vendas.obter(venda_id)
        if venda is None:
            raise RecursoNaoEncontrado("Venda nao encontrada.")
        venda.validar_retirada()
        assert venda.task_token is not None  # noqa: S101
        if venda.retirada_em:
            # A mesma solicitacao recupera um callback transitorio.
            # registradaEm e gerado pela API em cada tentativa.
            anterior = dict(venda.documentacao or {})
            atual = dict(documentacao)
            anterior.pop("registradaEm", None)
            atual.pop("registradaEm", None)
            if venda.retirada_em != retirada_em or anterior != atual:
                raise VendaNaoCancelavel("A retirada ja foi registrada com outros dados.")
        elif not self.vendas.registrar_retirada(venda_id, retirada_em, documentacao):
            raise VendaNaoCancelavel(
                "A venda nao aceita retirada (desistencia ou prazo encerrado)."
            )
        self.saga.enviar_sucesso(venda.task_token, {"retiradaEm": retirada_em})


__all__ = [
    "ConfirmarRetirada",
    "ConsultarVenda",
    "DesistirDaCompra",
    "IniciarCompra",
    "MotivoCancelamento",
]
