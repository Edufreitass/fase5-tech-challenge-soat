"""Consolida o OpenAPI 3.1 dos contextos em um unico documento (CI
compara
com o versionado).
"""

import json
import re
from typing import Any

from shared.http import AppRevenda
from shared.security import Papel

METODOS = ("get", "post", "put", "patch", "delete")

TAGS = {
    "Administracao": (
        "Administração",
        "Contexto de suporte à operação: funcionários, auditoria, solicitações LGPD, "
        "segredos e reprocessamento de fluxos.",
    ),
    "Clientes": (
        "Clientes",
        "Contexto responsável pelo perfil, consentimentos, proteção e direitos dos titulares.",
    ),
    "Mock": (
        "Simulador de pagamentos",
        "Integração simulada para desenvolvimento e demonstração do fluxo de pagamentos.",
    ),
    "Gestao": (
        "Gestão de veículos",
        "Visão operacional dos anúncios, restrita aos funcionários autorizados.",
    ),
    "Veiculos": (
        "Veículos",
        "Contexto do catálogo e do ciclo de vida dos anúncios de veículos.",
    ),
    "Vendas": (
        "Vendas",
        "Contexto de compra, reserva, pagamento, desistência e retirada do veículo.",
    ),
}

RESUMOS = {
    "Criar cobranca (mock)": "Criar cobrança simulada",
    "Cancelar cobranca (mock)": "Cancelar cobrança simulada",
    "Solicitar estorno (mock)": "Solicitar estorno simulado",
    "Simular pagamento (mock)": "Simular pagamento",
    "Cadastrar veiculo": "Cadastrar veículo",
    "Listar veiculos a venda (preco crescente)": "Listar veículos disponíveis por preço crescente",
    "Listar veiculos vendidos (preco crescente)": "Listar veículos vendidos por preço crescente",
    "Detalhar veiculo": "Consultar veículo",
    "Editar veiculo (If-Match)": "Atualizar veículo",
    "Inativar anuncio": "Inativar anúncio",
    "Reativar anuncio": "Reativar anúncio",
    "Listar veiculos (visao de gestao)": "Listar veículos para gestão",
    "Detalhar veiculo (visao de gestao)": "Consultar veículo para gestão",
    "Listar funcionarios": "Listar funcionários",
    "Convidar funcionario": "Convidar funcionário",
    "Alterar grupo ou ativar/desativar": "Atualizar grupo ou situação do funcionário",
    "Rotacionar a chave PII (recifra os dados)": (
        "Rotacionar a chave de proteção de dados pessoais"
    ),
    "Listar execucoes da saga por status": "Listar execuções de fluxos por situação",
    "Listar solicitacoes LGPD": "Listar solicitações LGPD",
    "Registrar aceite/revogacao de consentimento": (
        "Registrar aceite ou revogação de consentimento"
    ),
    "Historico de compras do cliente": "Consultar histórico de compras do cliente",
    "Dados para a documentacao do veiculo": "Consultar dados para documentação do veículo",
    "Consultar a trilha de auditoria (janela de ate 31 dias)": (
        "Consultar a trilha de auditoria (janela de até 31 dias)"
    ),
    "Cadastrar o proprio perfil": "Cadastrar o próprio perfil",
    "Consultar o proprio perfil (mascarado)": "Consultar o próprio perfil (dados protegidos)",
    "Atualizar o proprio perfil (If-Match)": "Atualizar o próprio perfil",
    "Exportar meus dados (LGPD, 1 por 24 h)": (
        "Exportar meus dados (LGPD; uma solicitação a cada 24 horas)"
    ),
    "Excluir/anonimizar meus dados (LGPD)": "Excluir ou anonimizar meus dados (LGPD)",
    "Informar se falta criar o primeiro administrador": (
        "Consultar situação da configuração inicial"
    ),
    "Convidar o administrador declarado na implantacao": "Convidar o administrador inicial",
    "Listar vendas por status (mais recentes primeiro)": (
        "Listar vendas por situação, das mais recentes para as mais antigas"
    ),
    "Iniciar compra (reserva o veiculo)": "Iniciar compra e reservar o veículo",
    "Consultar venda": "Consultar venda",
    "Confirmar retirada do veiculo": "Confirmar retirada do veículo",
}

CODIGOS_DE_SUCESSO = {
    ("post", "/clientes"): "201",
    ("post", "/configuracao-inicial"): "201",
    ("post", "/administracao/funcionarios"): "201",
    ("post", "/administracao/vendas/{venda_id}/fluxo/reprocessamento"): "202",
    ("post", "/administracao/segredos/webhook/rotacao"): "202",
    ("post", "/administracao/chaves-pii/rotacao"): "202",
    ("delete", "/clientes/meu-perfil"): "204",
    ("post", "/clientes/meu-perfil/consentimentos"): "201",
    ("post", "/veiculos"): "201",
    ("post", "/vendas"): "201",
    ("post", "/vendas/{venda_id}/desistencia"): "202",
    ("post", "/vendas/{venda_id}/retirada"): "202",
    ("post", "/_simulacao/pagamentos/cobrancas/{transacao_id}/simular"): "202",
}


def _caminho_openapi(caminho: str) -> str:
    return re.sub(r"<(\w+)>", r"{\1}", caminho)


def _padronizar_operacao(metodo: str, caminho: str, operacao: dict[str, Any]) -> None:
    resumo = operacao.get("summary", "")
    operacao["summary"] = RESUMOS.get(resumo, resumo)
    if operacao.get("tags"):
        original = operacao["tags"][0]
        operacao["tags"] = [TAGS.get(original, (original, ""))[0]]
    operacao.setdefault(
        "description",
        "A operação valida as regras do contexto de domínio responsável e retorna "
        "application/problem+json quando ocorre uma falha de negócio ou validação.",
    )
    for parametro in operacao.get("parameters", []):
        if parametro.get("in") == "path":
            parametro["description"] = "Identificador do recurso no contexto de domínio."
    for resposta in operacao.get("responses", {}).values():
        if resposta.get("description") == "Successful Response":
            resposta["description"] = "Operação concluída com sucesso."
        elif resposta.get("description") == "Validation Error":
            resposta["description"] = "A requisição contém dados ausentes ou inválidos."
            resposta["content"] = {
                "application/problem+json": {
                    "schema": {"$ref": "#/components/schemas/ProblemaHttp"}
                }
            }
    operacao.setdefault("responses", {}).setdefault(
        "default",
        {
            "description": "Falha de negócio, autenticação, autorização, recurso ou dependência.",
            "content": {
                "application/problem+json": {
                    "schema": {"$ref": "#/components/schemas/ProblemaHttp"}
                }
            },
        },
    )
    sucesso = CODIGOS_DE_SUCESSO.get((metodo, caminho))
    if sucesso and "200" in operacao["responses"]:
        resposta = operacao["responses"].pop("200")
        resposta["description"] = {
            "201": "Recurso criado com sucesso.",
            "202": "Solicitação aceita para processamento.",
            "204": "Operação concluída sem conteúdo de resposta.",
        }[sucesso]
        if sucesso == "204":
            resposta.pop("content", None)
        operacao["responses"][sucesso] = resposta
        operacao["responses"] = dict(sorted(operacao["responses"].items()))


def _aplicar_seguranca(operacao: dict[str, Any], papeis: tuple[Papel, ...]) -> None:
    if papeis == (Papel.SISTEMA,):
        operacao["security"] = [{"awsSigV4": []}]
    elif papeis != (Papel.ANONIMO,):
        esquema = "oauthClientes" if Papel.CLIENTE in papeis else "oauthFuncionarios"
        operacao["security"] = [{"bearerAuth": []}, {esquema: ["openid"]}]


def consolidar(apps: list[AppRevenda]) -> dict[str, Any]:
    consolidado: dict[str, Any] = {
        "openapi": "3.1.2",
        "info": {
            "title": "API da Plataforma de Revenda de Veículos",
            "version": "1.0.0",
            "summary": "API REST da plataforma de revenda de veículos.",
            "description": (
                "Contrato HTTP organizado por contextos de domínio: Clientes, Veículos, "
                "Vendas e Administração. Os contextos colaboram por casos de uso e eventos; "
                "detalhes de persistência e provedores externos permanecem internos. "
                "Erros seguem o formato application/problem+json. Os domínios OAuth2 de exemplo "
                "neste arquivo são substituídos pelos domínios configurados na documentação em "
                "execução."
            ),
        },
        "servers": [{"url": "/v1"}],
        "tags": [{"name": nome, "description": descricao} for nome, descricao in TAGS.values()],
        "paths": {},
        "components": {
            "schemas": {
                "ProblemaHttp": {
                    "type": "object",
                    "description": "Erro HTTP RFC 9457 com identificador de correlação.",
                    "required": ["type", "title", "status", "instance", "correlationId"],
                    "properties": {
                        "type": {
                            "type": "string",
                            "format": "uri-reference",
                            "description": "Tipo do problema.",
                        },
                        "title": {"type": "string", "description": "Resumo legível do problema."},
                        "status": {"type": "integer", "minimum": 400, "maximum": 599},
                        "detail": {
                            "type": "string",
                            "description": "Detalhes adicionais do problema, se disponíveis.",
                        },
                        "instance": {
                            "type": "string",
                            "description": "Caminho da requisição que originou o problema.",
                        },
                        "correlationId": {
                            "type": "string",
                            "description": "Identificador para rastrear a requisição.",
                        },
                    },
                    "additionalProperties": True,
                }
            },
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
                "oauthClientes": {
                    "type": "oauth2",
                    "description": "Autenticação de clientes; domínio definido por ambiente.",
                    "flows": {
                        "authorizationCode": {
                            "authorizationUrl": "https://clientes.auth.exemplo.invalid/oauth2/authorize",
                            "tokenUrl": "https://clientes.auth.exemplo.invalid/oauth2/token",
                            "scopes": {"openid": "Identidade", "email": "Endereço de e-mail"},
                        }
                    },
                },
                "oauthFuncionarios": {
                    "type": "oauth2",
                    "description": "Autenticação de funcionários; domínio definido por ambiente.",
                    "flows": {
                        "authorizationCode": {
                            "authorizationUrl": "https://funcionarios.auth.exemplo.invalid/oauth2/authorize",
                            "tokenUrl": "https://funcionarios.auth.exemplo.invalid/oauth2/token",
                            "scopes": {"openid": "Identidade", "email": "Endereço de e-mail"},
                        }
                    },
                },
                "awsSigV4": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "Authorization",
                    "description": "Acesso de serviço por assinatura AWS Signature Version 4.",
                },
            },
        },
    }
    for app in apps:
        parcial = json.loads(
            app.get_openapi_json_schema(title="x", version="1", openapi_version="3.1.0")
        )
        consolidado["components"]["schemas"].update(
            parcial.get("components", {}).get("schemas", {})
        )
        for caminho, operacoes in parcial["paths"].items():
            consolidado["paths"].setdefault(caminho, {}).update(operacoes)
        for metodo, caminho_rota, papeis in app.rotas:
            operacao = (
                consolidado["paths"].get(_caminho_openapi(caminho_rota), {}).get(metodo.lower())
            )
            if operacao is not None:
                _aplicar_seguranca(operacao, papeis)
    for caminho, operacoes in consolidado["paths"].items():
        for metodo, operacao in operacoes.items():
            if metodo in METODOS:
                _padronizar_operacao(metodo, caminho, operacao)
    consolidado["paths"] = dict(sorted(consolidado["paths"].items()))
    return consolidado
