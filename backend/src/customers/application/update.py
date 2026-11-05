"""Atualizacao do proprio perfil e consentimentos, com If-
Match (concorrencia otimista)."""

from collections.abc import Callable
from dataclasses import dataclass, field, replace

from customers.domain import rules as regras
from customers.domain.models import (
    Cliente,
    Consentimento,
    ConsentimentoVigente,
    Endereco,
    Finalidade,
    RgArmazenado,
    RgEntrada,
)
from customers.domain.ports import Cifrador, Hasher, RepositorioClientes, VendasEmAndamento
from customers.domain.rules import com_pendencias
from shared.errors import (
    ErroValidacao,
    PerfilClienteInexistente,
    RegraNegocioViolada,
    VersaoDesatualizada,
)
from shared.time import agora_iso


def _carregar(repo: RepositorioClientes, cliente_id: str, versao: int | None) -> Cliente:
    cliente = repo.obter(cliente_id)
    if cliente is None:
        raise PerfilClienteInexistente("Faca o cadastro em POST /clientes.")
    if versao is not None and cliente.versao != versao:
        raise VersaoDesatualizada("O perfil foi alterado; releia e tente de novo.")
    return cliente


@dataclass(frozen=True)
class MudancasPerfil:
    """So os campos enviados mudam; CPF, e-mail e consentimento nao sao
    editaveis aqui."""

    nome_completo: str | None = None
    telefone: str | None = None
    endereco: Endereco | None = None
    rg: RgEntrada | None = None
    cnh: str | None = None


@dataclass
class AtualizarCliente:
    repositorio: RepositorioClientes
    cifrador: Cifrador
    vendas: VendasEmAndamento
    versao_termo_vigente: str
    relogio: Callable[[], str] = field(default=agora_iso)

    def executar(self, cliente_id: str, mudancas: MudancasPerfil, versao_esperada: int) -> Cliente:
        atual = _carregar(self.repositorio, cliente_id, versao_esperada)
        if (mudancas.endereco or mudancas.rg) and self.vendas.possui(cliente_id):
            raise RegraNegocioViolada(
                "Endereco e RG nao podem ser alterados com compra em andamento."
            )
        erros: regras.Erros = []
        nome = (
            regras.normalizar_nome(mudancas.nome_completo, erros)
            if mudancas.nome_completo
            else atual.nome_completo
        )
        telefone = (
            regras.normalizar_telefone(mudancas.telefone, erros)
            if mudancas.telefone
            else atual.telefone
        )
        endereco = (
            regras.normalizar_endereco(mudancas.endereco, erros)
            if mudancas.endereco
            else atual.endereco
        )
        rg_entrada = regras.normalizar_rg(mudancas.rg, erros) if mudancas.rg else None
        cnh = regras.normalizar_cnh(mudancas.cnh, erros) if mudancas.cnh else None
        if erros:
            raise ErroValidacao(erros)
        rg = atual.rg
        if rg_entrada is not None:
            rg = RgArmazenado(
                numero_cifrado=self.cifrador.cifrar(
                    rg_entrada.numero, cliente_id=cliente_id, campo="rg"
                ),
                numero_final=rg_entrada.numero[-5:],
                numero_mascarado=regras.mascarar_rg(rg_entrada.numero),
                orgao_emissor=rg_entrada.orgao_emissor,
                uf=rg_entrada.uf,
            )
        novo = replace(
            atual,
            nome_completo=nome,
            telefone=telefone,
            endereco=endereco,
            rg=rg,
            cnh_cifrada=self.cifrador.cifrar(cnh, cliente_id=cliente_id, campo="cnh")
            if cnh
            else atual.cnh_cifrada,
            cnh_final=cnh[-4:] if cnh else atual.cnh_final,
            atualizado_em=self.relogio(),
            ultima_atividade_em=self.relogio(),
            versao=atual.versao + 1,
        )
        novo = com_pendencias(novo, self.versao_termo_vigente)
        inalterado = com_pendencias(atual, self.versao_termo_vigente)
        if (
            replace(
                novo,
                versao=atual.versao,
                atualizado_em=atual.atualizado_em,
                ultima_atividade_em=atual.ultima_atividade_em,
            )
            == inalterado
        ):
            return inalterado  # nada mudou: sem nova versao
        self.repositorio.atualizar(novo, versao_esperada)
        return novo


@dataclass
class RegistrarConsentimento:
    repositorio: RepositorioClientes
    hasher: Hasher
    versao_termo_vigente: str
    relogio: Callable[[], str] = field(default=agora_iso)

    def executar(  # noqa: PLR0913, PLR0917
        self,
        cliente_id: str,
        versao_termo: str,
        aceito: bool,
        finalidades: list[Finalidade],
        ip: str,
        user_agent: str,
    ) -> tuple[Consentimento, Cliente]:
        cliente = _carregar(self.repositorio, cliente_id, None)
        erros: regras.Erros = []
        if versao_termo != self.versao_termo_vigente:
            erros.append(
                {
                    "campo": "versaoTermo",
                    "mensagem": f"versao vigente do termo: {self.versao_termo_vigente}",
                }
            )
        if not finalidades:
            erros.append({"campo": "finalidades", "mensagem": "informe ao menos uma finalidade"})
        if erros:
            raise ErroValidacao(erros)
        contrato = Finalidade.EXECUCAO_CONTRATO in finalidades
        if contrato and not aceito:
            raise RegraNegocioViolada(
                "O aceite de EXECUCAO_CONTRATO nao pode ser revogado; solicite a exclusao."
            )
        agora = self.relogio()
        consentimento = Consentimento(
            versao_termo=versao_termo,
            finalidades=tuple(finalidades),
            aceito=aceito,
            aceito_em=agora,
            ip_hmac=self.hasher.hmac("ip", ip),
            user_agent=user_agent[:256],
        )
        vigente = ConsentimentoVigente(versao_termo, agora) if contrato else None
        self.repositorio.registrar_consentimento(cliente_id, consentimento, vigente, agora)
        atualizado = replace(cliente, consentimento_vigente=vigente) if vigente else cliente
        return consentimento, com_pendencias(atualizado, self.versao_termo_vigente)


__all__ = ["AtualizarCliente", "MudancasPerfil", "RegistrarConsentimento", "com_pendencias"]
