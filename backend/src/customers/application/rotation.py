"""Recifragem dos campos sensiveis para a nova versao da chave PII."""

from dataclasses import dataclass, replace
from typing import Protocol

from customers.domain.models import Cliente, RgArmazenado
from customers.domain.ports import CifradorVersionado, Decifrador
from shared.errors import ErroDecifragem, VersaoDesatualizada


class RepositorioRecifragem(Protocol):
    def todos_os_perfis(self) -> "list[Cliente]": ...

    def atualizar(self, cliente: Cliente, versao_esperada: int) -> None: ...

    def retencoes_legais(self) -> "list[tuple[str, str]]":
        """[(clienteId, cpfCifrado)] dos itens RETENCAO_LEGAL."""
        ...

    def atualizar_cpf_retencao(self, cliente_id: str, cpf_cifrado: str) -> None: ...


@dataclass
class RecifrarCampos:
    repositorio: RepositorioRecifragem
    decifrador: Decifrador
    cifrador: CifradorVersionado

    def _novo(self, cifrado: str, cliente_id: str, campo: str) -> str:
        if self.cifrador.na_versao_atual(cifrado):
            return cifrado  # idempotente: ja esta na versao nova
        claro = self.decifrador.decifrar(cifrado, cliente_id=cliente_id, campo=campo)
        return self.cifrador.cifrar(claro, cliente_id=cliente_id, campo=campo)

    def executar(self) -> dict[str, int]:
        recifrados = falhas = 0
        for cliente in self.repositorio.todos_os_perfis():
            try:
                rg = cliente.rg
                if rg is not None:
                    rg = RgArmazenado(
                        self._novo(rg.numero_cifrado, cliente.id, "rg"),
                        rg.numero_final,
                        rg.numero_mascarado,
                        rg.orgao_emissor,
                        rg.uf,
                    )
                novo = replace(
                    cliente,
                    cpf_cifrado=self._novo(cliente.cpf_cifrado, cliente.id, "cpf"),
                    rg=rg,
                    cnh_cifrada=self._novo(cliente.cnh_cifrada, cliente.id, "cnh")
                    if cliente.cnh_cifrada
                    else None,
                )
                if novo != cliente:
                    self.repositorio.atualizar(
                        replace(novo, versao=cliente.versao + 1), cliente.versao
                    )
                    recifrados += 1
            except (VersaoDesatualizada, ErroDecifragem):
                falhas += 1
        for cliente_id, cpf_cifrado in self.repositorio.retencoes_legais():
            try:
                novo_cpf = self._novo(cpf_cifrado, cliente_id, "cpf")
                if novo_cpf != cpf_cifrado:
                    self.repositorio.atualizar_cpf_retencao(cliente_id, novo_cpf)
                    recifrados += 1
            except ErroDecifragem:
                falhas += 1
        return {"recifrados": recifrados, "falhas": falhas}
