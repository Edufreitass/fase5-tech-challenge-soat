from collections.abc import Iterator
from typing import Any, Protocol

from customers.domain.models import (
    Cliente,
    Consentimento,
    ConsentimentoVigente,
    RetencaoLegal,
    SolicitacaoLgpd,
)


class RepositorioClientes(Protocol):
    def criar(self, cliente: Cliente, consentimento: Consentimento, *, email_hmac: str) -> None:
        """Grava perfil, consentimento e chaves de unicidade (CPF#,
        EMAIL#)
        atomicamente.

        Levanta `ConflitoUnicidade` se CPF, e-mail ou o proprio
        perfil
        ja existirem.
        """
        ...

    def obter(self, cliente_id: str) -> Cliente | None: ...

    def atualizar(self, cliente: Cliente, versao_esperada: int) -> None:
        """Substitui o perfil se `versao` ainda for a lida
        (`VersaoDesatualizada` senao)."""
        ...

    def status_do_perfil(self, cliente_id: str) -> str | None:
        """`ATIVO`/`ANONIMIZADO` ou None se nunca existiu."""
        ...

    def consentimentos(self, cliente_id: str) -> list[dict[str, Any]]: ...

    def ultima_exportacao(self, cliente_id: str) -> str | None:
        """`criadoEm` da ultima exportacao CONCLUIDA."""
        ...

    def registrar_solicitacao(self, solicitacao: SolicitacaoLgpd) -> None: ...

    def anonimizar(
        self,
        cliente: Cliente,
        *,
        email_hmac: str,
        retencao: RetencaoLegal | None,
        solicitacao: SolicitacaoLgpd,
        agora: str,
    ) -> None:
        """Substitui o perfil por um registro anonimo e remove
        CPF#/EMAIL#
        (atomico).
        """
        ...

    def inativos_desde(self, limite_iso: str) -> Iterator[Cliente]:
        """Perfis ATIVO com `ultimaAtividadeEm` anterior ao limite
        (Scan
        paginado).
        """
        ...

    def registrar_consentimento(
        self,
        cliente_id: str,
        consentimento: Consentimento,
        vigente: ConsentimentoVigente | None,
        agora: str,
    ) -> None:
        """Grava o aceite (append-only); com `vigente`, atualiza o
        perfil
        na mesma transacao.
        """
        ...


class VendasEmAndamento(Protocol):
    def possui(self, cliente_id: str) -> bool:
        """True se o cliente tem compra em andamento (lock
        `RESERVA_ATIVA`).
        """
        ...


class VendasDoCliente(Protocol):
    """Leitura das vendas do cliente (tabela `vendas`), para
    exportacao,
    exclusao e retencao.
    """

    def em_andamento(self, cliente_id: str) -> bool: ...

    def todas(self, cliente_id: str) -> list[dict[str, Any]]: ...

    def concluidas(self, cliente_id: str) -> list[tuple[str, str]]:
        """[(vendaId, atualizadoEm)] das vendas CONCLUIDO."""
        ...


class IdentidadeRemocao(Protocol):
    def remover(self, cliente_id: str) -> None:
        """Remove o usuario do pool de clientes; inexistente =
        sucesso.
        """
        ...


class Cifrador(Protocol):
    """Cifra campos com a chave PUBLICA (sealed box); nao consegue
    decifrar.
    """

    def cifrar(self, valor: str, *, cliente_id: str, campo: str) -> str: ...


class CifradorVersionado(Cifrador, Protocol):
    def na_versao_atual(self, cifrado: str) -> bool:
        """Verifica se o campo ja usa a chave de destino da
        recifragem.
        """
        ...


class Hasher(Protocol):
    def hmac(self, escopo: str, valor: str) -> str: ...


class Decifrador(Protocol):
    """Decifra com a chave PRIVADA; so existe na fn-clientes-interno /
    fn-
    lgpd-worker.
    """

    def decifrar(self, cifrado: str, *, cliente_id: str, campo: str) -> str: ...


class DiretorioIdentidade(Protocol):
    def obter_email(self, cliente_id: str) -> tuple[str, bool]:
        """(e-mail, verificado) do usuario no pool de clientes."""
        ...
