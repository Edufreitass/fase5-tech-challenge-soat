"""Listagens e documentacao de vendas."""

from dataclasses import dataclass
from typing import Any, Protocol

from sales.domain.models import StatusVenda, Venda
from sales.domain.ports import LeituraVenda, ListagemVendas
from shared.contracts import Cursor, DocumentacaoCliente
from shared.errors import ErroValidacao, RecursoNaoEncontrado, RegraNegocioViolada
from vehicles.domain.ports import RepositorioVeiculos

JUSTIFICATIVA_MIN = 10
JUSTIFICATIVA_MAX = 200


@dataclass
class ListarVendas:
    vendas: ListagemVendas

    def por_status(
        self, status: StatusVenda, *, limite: int, cursor: Cursor | None
    ) -> tuple[list[Venda], Cursor | None]:
        return self.vendas.listar_por_status(status, limite=limite, cursor=cursor)

    def do_cliente(
        self, cliente_id: str, *, limite: int, cursor: Cursor | None
    ) -> tuple[list[Venda], Cursor | None]:
        return self.vendas.listar_do_cliente(cliente_id, limite=limite, cursor=cursor)


class DadosDocumentacao(Protocol):
    def obter_dados_documentacao(self, cliente_id: str) -> DocumentacaoCliente: ...


class Auditoria(Protocol):
    def publicar(self, tipo: str, dados: dict[str, Any]) -> None: ...


@dataclass
class ObterDocumentacao:
    """Dados completos para a transferencia do veiculo (so com a venda
    PAGA), com justificativa
    obrigatoria e evento de auditoria `DadosPessoaisAcessados`."""

    vendas: LeituraVenda
    veiculos: RepositorioVeiculos
    clientes: DadosDocumentacao
    auditoria: Auditoria

    def executar(
        self, venda_id: str, justificativa: str | None, ator_id: str, papel: str
    ) -> dict[str, Any]:
        texto = (justificativa or "").strip()
        if not JUSTIFICATIVA_MIN <= len(texto) <= JUSTIFICATIVA_MAX:
            raise ErroValidacao(
                [
                    {
                        "campo": "X-Justificativa",
                        "mensagem": (
                            f"informe de {JUSTIFICATIVA_MIN} a {JUSTIFICATIVA_MAX} caracteres"
                        ),
                    }
                ]
            )
        venda = self.vendas.obter(venda_id)
        if venda is None:
            raise RecursoNaoEncontrado("Venda nao encontrada.")
        if venda.status != StatusVenda.PAGO:
            raise RegraNegocioViolada("A documentacao so esta disponivel com a venda PAGA.")
        veiculo = self.veiculos.obter(venda.veiculo_id)
        if veiculo is None:
            raise RecursoNaoEncontrado("Veiculo da venda nao encontrado.")
        comprador = self.clientes.obter_dados_documentacao(venda.cliente_id)
        self.auditoria.publicar(
            "DadosPessoaisAcessados",
            {
                "vendaId": venda.id,
                "clienteId": venda.cliente_id,
                "atorId": ator_id,
                "papel": papel,
                "justificativa": texto,
                "finalidade": "DOCUMENTACAO",
            },
        )
        return {
            "vendaId": venda.id,
            "comprador": comprador,
            "veiculo": {
                "id": veiculo.id,
                "placa": veiculo.placa,
                "renavam": veiculo.renavam,
                "chassi": veiculo.chassi,
                "marca": veiculo.marca,
                "modelo": veiculo.modelo,
                "anoModelo": veiculo.ano_modelo,
            },
        }
