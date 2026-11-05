"""Executor das migracoes (equivalente ao Flyway): ordem, checksum,
historico no SSM."""

import json
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from migration_runner.domain.models import PADRAO_PARAM, Migracao, MigracaoInvalida, Operacao
from migration_runner.domain.ports import (
    CadastroVeiculos,
    DiretorioFuncionarios,
    RepositorioParametros,
)
from shared.contracts import MigracaoAplicada
from shared.errors import RegraNegocioViolada


class ChecksumDivergente(RegraNegocioViolada):
    titulo = "Migracao ja aplicada foi alterada"


@dataclass
class ExecutorMigracoes:
    parametros: RepositorioParametros
    funcionarios: DiretorioFuncionarios
    gerar_chaves: Callable[[], tuple[str, str]]
    veiculos: CadastroVeiculos | None = None
    relogio: Callable[[], datetime] = lambda: datetime.now(UTC)

    def executar(self, migracoes: list[Migracao]) -> list[MigracaoAplicada]:
        """Aplica as pendentes em ordem crescente; retorna so versoes
        aplicadas e duracao."""
        versoes = [m.versao for m in migracoes]
        if versoes != sorted(set(versoes)):
            raise MigracaoInvalida("Versoes de migracao duplicadas ou fora de ordem.")
        aplicadas: list[MigracaoAplicada] = []
        for migracao in migracoes:
            historico = self.parametros.ler(f"migracoes/{migracao.chave}")
            if historico is not None:
                if json.loads(historico)["checksum"] != migracao.checksum:
                    raise ChecksumDivergente(
                        f"{migracao.chave} foi alterada apos aplicada; crie outra versao."
                    )
                continue
            inicio = time.monotonic()
            for operacao in migracao.operacoes:
                self._aplicar(operacao)
            duracao = int((time.monotonic() - inicio) * 1000)
            self.parametros.gravar(
                f"migracoes/{migracao.chave}",
                json.dumps(
                    {
                        "checksum": migracao.checksum,
                        "aplicadaEm": self.relogio().isoformat(),
                        "duracaoMs": duracao,
                    }
                ),
                segredo=False,
                sobrescrever=False,
            )
            aplicadas.append({"versao": migracao.chave, "duracaoMs": duracao})
        return aplicadas

    # -- operacoes do catalogo
    # -------------------------------------------------
    def _aplicar(self, operacao: Operacao) -> None:
        p = operacao.parametros
        if operacao.nome == "ssm.gerar_segredo":
            self.parametros.gravar(
                f"segredos/{p['nome']}",
                secrets.token_urlsafe(int(p["bytes"])),
                segredo=True,
                sobrescrever=False,
            )
        elif operacao.nome == "ssm.gerar_par_chaves_pii":
            self._gerar_par_pii(int(p["versao"]))
        elif operacao.nome == "veiculos.cadastrar":
            if self.veiculos is None:
                raise MigracaoInvalida("Cadastro de veiculos nao configurado.")
            for item in p["itens"]:
                self.veiculos.cadastrar(item)
        elif operacao.nome == "cognito.criar_funcionario":
            self.funcionarios.garantir_funcionario(
                email=self._resolver(str(p["email"])), nome=str(p["nome"]), grupo=str(p["grupo"])
            )

        else:
            raise MigracaoInvalida(f"Operacao fora do catalogo: {operacao.nome}")

    def _gerar_par_pii(self, versao: int) -> None:
        if self.parametros.existe(f"pii/chave-publica-v{versao}"):
            return
        privada, publica = self.gerar_chaves()
        self.parametros.gravar(
            f"segredos/pii-chave-privada-v{versao}", privada, segredo=True, sobrescrever=False
        )
        self.parametros.gravar(
            f"pii/chave-publica-v{versao}", publica, segredo=False, sobrescrever=False
        )
        self.parametros.gravar("pii/versao-atual", str(versao), segredo=False, sobrescrever=True)

    def _resolver(self, texto: str) -> str:
        def substituir(casado: re.Match[str]) -> str:
            nome = casado.group(1)
            valor = self.parametros.ler(f"params/{nome}")
            if valor is None:
                raise MigracaoInvalida(f"Parametro params/{nome} nao encontrado.")
            return valor

        return PADRAO_PARAM.sub(substituir, texto)
