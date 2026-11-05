from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class StatusCliente(StrEnum):
    ATIVO = "ATIVO"
    ANONIMIZADO = "ANONIMIZADO"


class Finalidade(StrEnum):
    EXECUCAO_CONTRATO = "EXECUCAO_CONTRATO"
    MARKETING = "MARKETING"


UFS = frozenset(
    [
        "AC",
        "AL",
        "AP",
        "AM",
        "BA",
        "CE",
        "DF",
        "ES",
        "GO",
        "MA",
        "MT",
        "MS",
        "MG",
        "PA",
        "PB",
        "PR",
        "PE",
        "PI",
        "RJ",
        "RN",
        "RS",
        "RO",
        "RR",
        "SC",
        "SP",
        "SE",
        "TO",
    ]
)


@dataclass(frozen=True)
class Endereco:
    cep: str
    logradouro: str
    numero: str
    bairro: str
    cidade: str
    uf: str
    complemento: str | None = None


@dataclass(frozen=True)
class RgEntrada:
    numero: str
    orgao_emissor: str
    uf: str


@dataclass(frozen=True)
class ConsentimentoEntrada:
    versao_termo: str
    aceito: bool
    finalidades: tuple[Finalidade, ...]


@dataclass(frozen=True)
class NovoCliente:
    """Comando de cadastro; `id` e `email` vem do token validado, nunca
    do
    corpo.
    """

    id: str
    email: str
    email_verificado: bool
    nome_completo: str
    cpf: str
    data_nascimento: date
    telefone: str
    endereco: Endereco
    consentimento: ConsentimentoEntrada
    rg: RgEntrada | None = None
    ip: str = ""
    user_agent: str = ""


@dataclass(frozen=True)
class RgArmazenado:
    numero_cifrado: str
    numero_final: str
    numero_mascarado: str
    orgao_emissor: str
    uf: str


@dataclass(frozen=True)
class ConsentimentoVigente:
    versao_termo: str
    aceito_em: str


@dataclass(frozen=True)
class Consentimento:
    versao_termo: str
    finalidades: tuple[Finalidade, ...]
    aceito: bool
    aceito_em: str
    ip_hmac: str
    user_agent: str


@dataclass(frozen=True)
class SolicitacaoLgpd:
    """Registro de exportacao/exclusao (direitos do titular)."""

    id: str
    cliente_id: str
    operacao: str  # EXPORTACAO | EXCLUSAO
    status: str  # CONCLUIDA | REJEITADA
    criado_em: str
    motivo_rejeicao: str | None = None  # VENDA_EM_ANDAMENTO | LIMITE_DIARIO


@dataclass(frozen=True)
class RetencaoLegal:
    """Dados minimos de quem comprou e pediu exclusao: mantidos 5 anos
    apos
    a ultima venda.
    """

    cliente_id: str
    nome_completo: str
    cpf_cifrado: str
    vendas: tuple[str, ...]
    expira_em: int  # epoch seconds (TTL)


@dataclass(frozen=True)
class Cliente:
    id: str
    nome_completo: str
    cpf_cifrado: str
    cpf_hmac: str
    cpf_final: str
    data_nascimento: date
    email: str
    email_verificado: bool
    telefone: str
    endereco: Endereco
    consentimento_vigente: ConsentimentoVigente
    status: StatusCliente
    criado_em: str
    atualizado_em: str
    ultima_atividade_em: str
    versao: int
    rg: RgArmazenado | None = None
    cnh_cifrada: str | None = None
    cnh_final: str | None = None
    campos_pendentes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def cadastro_completo(self) -> bool:
        return not self.campos_pendentes

    @property
    def apto_para_compra(self) -> bool:
        return self.status == StatusCliente.ATIVO and self.cadastro_completo
