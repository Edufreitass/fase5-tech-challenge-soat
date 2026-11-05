from dataclasses import dataclass

from customers.domain.models import Cliente
from customers.domain.ports import Decifrador, DiretorioIdentidade, RepositorioClientes
from customers.domain.rules import com_pendencias
from shared.contracts import DadosCobranca, DadosTitular, DocumentacaoCliente, ValidacaoComprador
from shared.errors import PerfilClienteInexistente, RegraNegocioViolada


@dataclass
class ConsultarCliente:
    repositorio: RepositorioClientes

    def meu_perfil(self, cliente_id: str, versao_termo_vigente: str) -> Cliente:
        """Sempre mascarado: nao decifra nada (usa
        `cpf_final`/`numero_final`).
        """
        cliente = self.repositorio.obter(cliente_id)
        if cliente is None:
            raise PerfilClienteInexistente("Faca o cadastro em POST /clientes.")
        return com_pendencias(cliente, versao_termo_vigente)


@dataclass
class ValidarComprador:
    """Operacao interna `VALIDAR_COMPRADOR` (usada pela reserva)."""

    repositorio: RepositorioClientes

    def executar(self, cliente_id: str, versao_termo_vigente: str) -> ValidacaoComprador:
        cliente = self.repositorio.obter(cliente_id)
        if cliente is None:
            return {"valido": False, "camposPendentes": ["cadastro"]}
        cliente = com_pendencias(cliente, versao_termo_vigente)
        return {
            "valido": cliente.apto_para_compra,
            "camposPendentes": list(cliente.campos_pendentes),
        }


@dataclass
class ObterDadosCobranca:
    """Operacao interna `OBTER_DADOS_COBRANCA`: nome e CPF em claro;
    nao
    persiste nem loga.
    """

    repositorio: RepositorioClientes
    decifrador: Decifrador

    def executar(self, cliente_id: str) -> DadosCobranca:
        cliente = self.repositorio.obter(cliente_id)
        if cliente is None:
            raise RegraNegocioViolada("Cliente inexistente.")
        cpf = self.decifrador.decifrar(cliente.cpf_cifrado, cliente_id=cliente_id, campo="cpf")
        return {"nomeCompleto": cliente.nome_completo, "cpf": cpf}


@dataclass
class ObterDadosDocumentacao:
    """Operacao interna `OBTER_DADOS_DOCUMENTACAO`: dados
    completos,
    decifrados na hora.
    """

    repositorio: RepositorioClientes
    decifrador: Decifrador

    def executar(self, cliente_id: str) -> DocumentacaoCliente:
        c = self.repositorio.obter(cliente_id)
        if c is None:
            raise RegraNegocioViolada("Cliente inexistente.")
        e = c.endereco
        return {
            "nomeCompleto": c.nome_completo,
            "cpf": self.decifrador.decifrar(c.cpf_cifrado, cliente_id=cliente_id, campo="cpf"),
            "rg": {
                "numero": self.decifrador.decifrar(
                    c.rg.numero_cifrado, cliente_id=cliente_id, campo="rg"
                ),
                "orgaoEmissor": c.rg.orgao_emissor,
                "uf": c.rg.uf,
            }
            if c.rg
            else None,
            "dataNascimento": c.data_nascimento.isoformat(),
            "endereco": {
                "cep": e.cep,
                "logradouro": e.logradouro,
                "numero": e.numero,
                "complemento": e.complemento,
                "bairro": e.bairro,
                "cidade": e.cidade,
                "uf": e.uf,
            },
        }


@dataclass
class ExportarDadosTitular:
    """Operacao interna `EXPORTAR_DADOS`: todos os dados pessoais do
    titular, decifrados."""

    repositorio: RepositorioClientes
    decifrador: Decifrador

    def executar(self, cliente_id: str) -> DadosTitular:
        c = self.repositorio.obter(cliente_id)
        if c is None:
            raise RegraNegocioViolada("Cliente inexistente.")
        base = ObterDadosDocumentacao(self.repositorio, self.decifrador).executar(cliente_id)
        return {
            **base,
            "email": c.email,
            "telefone": c.telefone,
            "status": c.status.value,
            "criadoEm": c.criado_em,
            "cnh": self.decifrador.decifrar(c.cnh_cifrada, cliente_id=cliente_id, campo="cnh")
            if c.cnh_cifrada
            else None,
        }


__all__ = [
    "ConsultarCliente",
    "DiretorioIdentidade",
    "ExportarDadosTitular",
    "ObterDadosCobranca",
    "ObterDadosDocumentacao",
    "ValidarComprador",
]
