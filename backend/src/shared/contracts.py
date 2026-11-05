"""Contratos de dados puros compartilhados entre contextos."""

from typing import TypedDict

# Cursores de listagem contem apenas as chaves textuais do indice.
type Cursor = dict[str, str]


class ValidacaoComprador(TypedDict):
    valido: bool
    camposPendentes: list[str]


class DadosCobranca(TypedDict):
    nomeCompleto: str
    cpf: str


class EnderecoTitular(TypedDict):
    cep: str
    logradouro: str
    numero: str
    complemento: str | None
    bairro: str
    cidade: str
    uf: str


class RgTitular(TypedDict):
    numero: str
    orgaoEmissor: str
    uf: str


class DocumentacaoCliente(DadosCobranca):
    rg: RgTitular | None
    dataNascimento: str
    endereco: EnderecoTitular


class DadosTitular(DocumentacaoCliente):
    email: str
    telefone: str
    status: str
    criadoEm: str
    cnh: str | None


class SnapshotVeiculo(TypedDict, total=False):
    id: str
    marca: str
    modelo: str
    anoModelo: int
    cor: str


class DocumentacaoRetirada(TypedDict, total=False):
    status: str
    protocolo: str
    emitidaEm: str
    responsavelId: str
    registradaEm: str


class PrazosCompra(TypedDict):
    pagamentoSegundos: int
    retiradaSegundos: int


class EntradaSaga(TypedDict):
    vendaId: str
    veiculoId: str
    clienteId: str
    valorCentavos: int
    correlationId: str
    prazos: PrazosCompra


class MigracaoAplicada(TypedDict):
    versao: str
    duracaoMs: int
