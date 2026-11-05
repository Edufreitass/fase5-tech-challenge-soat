"""Regras de validacao do cadastro de cliente e de
`cadastroCompleto`.
"""

import re
from dataclasses import replace
from datetime import date

from customers.domain.brazilian_tax_id import cpf_valido, somente_digitos
from customers.domain.models import UFS, Cliente, Endereco, NovoCliente, RgArmazenado, RgEntrada
from shared.errors import ErroValidacao
from shared.masking import MASCARA
from shared.text import normalizar_texto

IDADE_MINIMA = 18
IDADE_MAXIMA = 120
_TELEFONE = re.compile(r"^\+[1-9][0-9]{9,14}$")


def idade(nascimento: date, hoje: date) -> int:
    anos = hoje.year - nascimento.year
    return anos - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))


def mascarar_rg(numero: str) -> str:
    """Mantem os 5 ultimos caracteres: ``12.345.678-9`` ->
    ``**.***.678-9``.
    """
    corpo, final = numero[:-5], numero[-5:]
    return "".join(MASCARA[0] if c.isalnum() else c for c in corpo) + final


Erros = list[dict[str, str]]


def normalizar_nome(valor: str, erros: Erros) -> str:
    nome = normalizar_texto(valor)
    if not 3 <= len(nome) <= 120:  # noqa: PLR2004
        erros.append({"campo": "nomeCompleto", "mensagem": "deve ter entre 3 e 120 caracteres"})
    return nome


def normalizar_telefone(valor: str, erros: Erros) -> str:
    telefone = normalizar_texto(valor)
    if not _TELEFONE.match(telefone):
        erros.append(
            {"campo": "telefone", "mensagem": "use o formato E.164 (ex.: +5511987654321)"}
        )
    return telefone


def normalizar_endereco(e: Endereco, erros: Erros) -> Endereco:
    cep = somente_digitos(e.cep)
    uf = e.uf.upper()
    if len(cep) != 8:  # noqa: PLR2004
        erros.append({"campo": "endereco.cep", "mensagem": "CEP deve ter 8 digitos"})
    if uf not in UFS:
        erros.append({"campo": "endereco.uf", "mensagem": "UF invalida"})
    for campo, valor, maximo in (
        ("logradouro", e.logradouro, 120),
        ("numero", e.numero, 10),
        ("bairro", e.bairro, 80),
        ("cidade", e.cidade, 80),
    ):
        if not 1 <= len(normalizar_texto(valor)) <= maximo:
            erros.append(
                {
                    "campo": f"endereco.{campo}",
                    "mensagem": f"deve ter entre 1 e {maximo} caracteres",
                }
            )
    if e.complemento is not None and len(normalizar_texto(e.complemento)) > 60:  # noqa: PLR2004
        erros.append(
            {"campo": "endereco.complemento", "mensagem": "deve ter no maximo 60 caracteres"}
        )
    return Endereco(
        cep=cep,
        logradouro=normalizar_texto(e.logradouro),
        numero=normalizar_texto(e.numero),
        bairro=normalizar_texto(e.bairro),
        cidade=normalizar_texto(e.cidade),
        uf=uf,
        complemento=normalizar_texto(e.complemento) if e.complemento else None,
    )


def normalizar_rg(rg: RgEntrada, erros: Erros) -> RgEntrada:
    numero, orgao = normalizar_texto(rg.numero), normalizar_texto(rg.orgao_emissor)
    if not 5 <= len(numero) <= 20:  # noqa: PLR2004
        erros.append({"campo": "rg.numero", "mensagem": "deve ter entre 5 e 20 caracteres"})
    if not 2 <= len(orgao) <= 10:  # noqa: PLR2004
        erros.append({"campo": "rg.orgaoEmissor", "mensagem": "deve ter entre 2 e 10 caracteres"})
    if rg.uf.upper() not in UFS:
        erros.append({"campo": "rg.uf", "mensagem": "UF invalida"})
    return RgEntrada(numero, orgao, rg.uf.upper())


def normalizar_cnh(valor: str, erros: Erros) -> str:
    cnh = somente_digitos(valor)
    if len(cnh) != 11:  # noqa: PLR2004
        erros.append({"campo": "cnh", "mensagem": "CNH deve ter 11 digitos"})
    return cnh


def validar_e_normalizar(novo: NovoCliente, hoje: date, versao_vigente: str) -> NovoCliente:
    """Retorna o comando normalizado ou levanta `ErroValidacao` com
    todos
    os erros de campo.
    """
    erros: Erros = []
    nome = normalizar_nome(novo.nome_completo, erros)
    if not cpf_valido(novo.cpf):
        erros.append({"campo": "cpf", "mensagem": "CPF invalido (digito verificador)"})
    anos = idade(novo.data_nascimento, hoje) if novo.data_nascimento <= hoje else -1
    if anos < 0 or anos > IDADE_MAXIMA:
        erros.append({"campo": "dataNascimento", "mensagem": "data invalida"})
    elif anos < IDADE_MINIMA:
        erros.append({"campo": "dataNascimento", "mensagem": "o titular deve ter 18 anos ou mais"})
    telefone = normalizar_telefone(novo.telefone, erros)
    endereco = normalizar_endereco(novo.endereco, erros)
    rg = normalizar_rg(novo.rg, erros) if novo.rg is not None else None

    c = novo.consentimento
    if not c.aceito:
        erros.append(
            {
                "campo": "consentimento.aceito",
                "mensagem": "o consentimento e obrigatorio para o cadastro",
            }
        )
    if c.versao_termo != versao_vigente:
        erros.append(
            {
                "campo": "consentimento.versaoTermo",
                "mensagem": f"versao vigente do termo: {versao_vigente}",
            }
        )
    if not any(f.value == "EXECUCAO_CONTRATO" for f in c.finalidades):
        erros.append(
            {"campo": "consentimento.finalidades", "mensagem": "EXECUCAO_CONTRATO e obrigatoria"}
        )

    if erros:
        raise ErroValidacao(erros)
    return NovoCliente(
        id=novo.id,
        email=novo.email,
        email_verificado=novo.email_verificado,
        nome_completo=nome,
        cpf=somente_digitos(novo.cpf),
        data_nascimento=novo.data_nascimento,
        telefone=telefone,
        endereco=endereco,
        consentimento=c,
        rg=rg,
        ip=novo.ip,
        user_agent=novo.user_agent[:256],
    )


def campos_pendentes(
    *, rg: RgArmazenado | None, email_verificado: bool, consentimento_vigente: bool
) -> tuple[str, ...]:
    """Pre-condicao da compra: o que ainda falta para `cadastroCompleto`
    (RG
    so para comprar).
    """
    pendentes = []
    if rg is None:
        pendentes.append("rg")
    if not email_verificado:
        pendentes.append("email")
    if not consentimento_vigente:
        pendentes.append("consentimento")
    return tuple(pendentes)


def com_pendencias(cliente: Cliente, versao_vigente: str) -> Cliente:
    """Recalcula `camposPendentes` contra a versao vigente do termo
    (muda
    sem migrar dados).
    """
    pendentes = campos_pendentes(
        rg=cliente.rg,
        email_verificado=cliente.email_verificado,
        consentimento_vigente=cliente.consentimento_vigente.versao_termo == versao_vigente,
    )
    return replace(cliente, campos_pendentes=pendentes)
