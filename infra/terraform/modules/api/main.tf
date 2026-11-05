variable "nome" {
  type = string
}

variable "stage" {
  type    = string
  default = "v1"
}

variable "regiao" {
  type = string
}

variable "provider_arns" {
  description = "Pools do Cognito Authorizer (clientes e funcionarios)."
  type        = list(string)
}

variable "rotas" {
  description = "Rotas: chave '<METODO> <caminho>' => { lambda_nome, acesso (publico|cognito|iam) }. O nome e estatico para nao criar ciclo com as Lambdas."
  type = map(object({
    lambda_nome = string
    acesso      = string
  }))
}

variable "throttling" {
  type = object({ stage_rps = number, stage_burst = number })
}

variable "throttling_rotas" {
  description = "Limite (rps) por rota: chave '<caminho sem barra inicial>/<METODO>' (ex.: clientes/POST)."
  type        = map(number)
  default     = {}
}

variable "xray" {
  type    = bool
  default = true
}

data "aws_caller_identity" "atual" {}

locals {
  conta = data.aws_caller_identity.atual.account_id
  rotas_por_caminho = {
    for caminho in distinct([for k, _ in var.rotas : split(" ", k)[1]]) : caminho => {
      for k, r in var.rotas : lower(split(" ", k)[0]) => r if split(" ", k)[1] == caminho
    }
  }

  # access tokens exigem escopo no metodo (authorization_scopes), senao o API Gateway espera id token.
  openapi = {
    openapi = "3.0.1"
    info    = { title = var.nome, version = "1.0.0" }
    components = {
      securitySchemes = {
        cognito = {
          type                           = "apiKey"
          name                           = "Authorization"
          in                             = "header"
          "x-amazon-apigateway-authtype" = "cognito_user_pools"
          "x-amazon-apigateway-authorizer" = {
            type         = "cognito_user_pools"
            providerARNs = var.provider_arns
          }
        }
        sigv4 = {
          type                           = "apiKey"
          name                           = "Authorization"
          in                             = "header"
          "x-amazon-apigateway-authtype" = "awsSigv4"
        }
      }
    }
    paths = {
      for caminho, metodos in local.rotas_por_caminho : caminho => {
        for metodo, r in metodos : metodo => merge(
          {
            responses = { "200" = { description = "ok" } }
            "x-amazon-apigateway-integration" = {
              type                = "aws_proxy"
              httpMethod          = "POST"
              uri                 = "arn:aws:apigateway:${var.regiao}:lambda:path/2015-03-31/functions/arn:aws:lambda:${var.regiao}:${local.conta}:function:${r.lambda_nome}/invocations"
              passthroughBehavior = "when_no_match"
            }
          },
          # O authorizer aceita o token que tiver QUALQUER um dos escopos: login hospedado (openid) ou
          # autenticacao direta/SRP (aws.cognito.signin.user.admin). Dois requisitos separados nao sao permitidos.
          r.acesso == "cognito" ? { security = [{ cognito = ["openid", "aws.cognito.signin.user.admin"] }] } : {},
          r.acesso == "iam" ? { security = [{ sigv4 = [] }] } : {},
        )
      }
    }
  }
}

resource "aws_api_gateway_rest_api" "api" {
  name                         = var.nome
  body                         = jsonencode(local.openapi)
  disable_execute_api_endpoint = false

  lifecycle {
    create_before_destroy = true
  }

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_api_gateway_deployment" "api" {
  rest_api_id = aws_api_gateway_rest_api.api.id

  triggers = {
    # gateway responses so valem apos um novo deployment
    redeploy = sha1(jsonencode([local.openapi, local.respostas_gateway]))
  }

  depends_on = [aws_api_gateway_gateway_response.problema]

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "v1" {
  rest_api_id           = aws_api_gateway_rest_api.api.id
  deployment_id         = aws_api_gateway_deployment.api.id
  stage_name            = var.stage
  xray_tracing_enabled  = var.xray
  cache_cluster_enabled = false
}

resource "aws_api_gateway_method_settings" "geral" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  stage_name  = aws_api_gateway_stage.v1.stage_name
  method_path = "*/*"

  settings {
    throttling_rate_limit  = var.throttling.stage_rps
    throttling_burst_limit = var.throttling.stage_burst
    metrics_enabled        = false # metricas detalhadas sao pagas
    caching_enabled        = false
  }
}

resource "aws_api_gateway_method_settings" "rota" {
  for_each    = var.throttling_rotas
  rest_api_id = aws_api_gateway_rest_api.api.id
  stage_name  = aws_api_gateway_stage.v1.stage_name
  method_path = each.key

  settings {
    throttling_rate_limit  = each.value
    throttling_burst_limit = each.value * 2
    metrics_enabled        = false
    caching_enabled        = false
  }

  depends_on = [aws_api_gateway_method_settings.geral]
}

# Erros gerados pelo proprio API Gateway (401/403/404/429/5xx) saem com corpo no formato problem+json
# (RFC 9457). O API Gateway nao permite trocar o Content-Type dessas respostas: ele permanece
# application/json; as respostas das Lambdas usam application/problem+json.
locals {
  respostas_gateway = {
    UNAUTHORIZED                 = { status = "401", slug = "nao-autenticado", titulo = "Autenticacao necessaria" }
    ACCESS_DENIED                = { status = "403", slug = "acesso-negado", titulo = "Acesso negado" }
    MISSING_AUTHENTICATION_TOKEN = { status = "404", slug = "recurso-nao-encontrado", titulo = "Recurso nao encontrado" }
    THROTTLED                    = { status = "429", slug = "limite-excedido", titulo = "Limite de requisicoes excedido" }
    DEFAULT_5XX                  = { status = "$context.status", slug = "erro-interno", titulo = "Erro interno" }
  }
}

resource "aws_api_gateway_gateway_response" "problema" {
  for_each      = local.respostas_gateway
  rest_api_id   = aws_api_gateway_rest_api.api.id
  response_type = each.key
  status_code   = can(tonumber(each.value.status)) ? each.value.status : null

  response_templates = {
    "application/json" = format(
      "{\"type\":\"urn:revenda:problema:%s\",\"title\":\"%s\",\"status\":%s,\"correlationId\":\"$context.requestId\"}",
      each.value.slug, each.value.titulo, each.value.status,
    )
  }
}

output "nome" {
  value = aws_api_gateway_rest_api.api.name
}

output "stage" {
  value = aws_api_gateway_stage.v1.stage_name
}

output "id" {
  value = aws_api_gateway_rest_api.api.id
}

# Derivada so do id da API (evita ciclo com Lambdas que recebem a URL em variaveis de ambiente).
output "url_base" {
  value = "https://${aws_api_gateway_rest_api.api.id}.execute-api.${var.regiao}.amazonaws.com/${var.stage}"
}

output "execution_arn" {
  value = aws_api_gateway_rest_api.api.execution_arn
}
