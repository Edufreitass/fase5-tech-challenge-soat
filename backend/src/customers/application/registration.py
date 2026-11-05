"""Caso de uso: cadastrar o perfil do comprador."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from customers.domain import rules as regras
from customers.domain.brazilian_tax_id import somente_digitos
from customers.domain.models import (
    Cliente,
    Consentimento,
    ConsentimentoVigente,
    NovoCliente,
    RgArmazenado,
    StatusCliente,
)
from customers.domain.ports import Cifrador, Hasher, RepositorioClientes
from shared.time import agora_iso


def hoje_utc() -> date:
    return datetime.now(UTC).date()


@dataclass
class CadastrarCliente:
    repositorio: RepositorioClientes
    cifrador: Cifrador
    hasher: Hasher
    versao_termo_vigente: str
    relogio: Callable[[], str] = field(default=agora_iso)
    hoje: Callable[[], date] = field(default=hoje_utc)

    def executar(self, comando: NovoCliente) -> Cliente:
        novo = regras.validar_e_normalizar(comando, self.hoje(), self.versao_termo_vigente)
        agora = self.relogio()
        rg = None
        if novo.rg is not None:
            rg = RgArmazenado(
                numero_cifrado=self.cifrador.cifrar(
                    novo.rg.numero, cliente_id=novo.id, campo="rg"
                ),
                numero_final=novo.rg.numero[-5:],
                numero_mascarado=regras.mascarar_rg(novo.rg.numero),
                orgao_emissor=novo.rg.orgao_emissor,
                uf=novo.rg.uf,
            )
        cliente = Cliente(
            id=novo.id,
            nome_completo=novo.nome_completo,
            cpf_cifrado=self.cifrador.cifrar(novo.cpf, cliente_id=novo.id, campo="cpf"),
            cpf_hmac=self.hasher.hmac("cpf", somente_digitos(novo.cpf)),
            cpf_final=novo.cpf[-5:],
            data_nascimento=novo.data_nascimento,
            email=novo.email,
            email_verificado=novo.email_verificado,
            telefone=novo.telefone,
            endereco=novo.endereco,
            consentimento_vigente=ConsentimentoVigente(novo.consentimento.versao_termo, agora),
            status=StatusCliente.ATIVO,
            criado_em=agora,
            atualizado_em=agora,
            ultima_atividade_em=agora,
            versao=1,
            rg=rg,
            campos_pendentes=regras.campos_pendentes(
                rg=rg, email_verificado=novo.email_verificado, consentimento_vigente=True
            ),
        )
        consentimento = Consentimento(
            versao_termo=novo.consentimento.versao_termo,
            finalidades=novo.consentimento.finalidades,
            aceito=True,
            aceito_em=agora,
            ip_hmac=self.hasher.hmac("ip", novo.ip),
            user_agent=novo.user_agent,
        )
        self.repositorio.criar(
            cliente, consentimento, email_hmac=self.hasher.hmac("email", novo.email.lower())
        )
        return cliente
