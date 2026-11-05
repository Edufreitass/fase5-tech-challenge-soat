# --- Parametros nao sensiveis --------------------------------------
locals {
  parametros = {
    "params/prazo-pagamento-segundos" = tostring(local.neg.prazo_pagamento_segundos)
    "params/prazo-retirada-segundos"  = tostring(local.neg.prazo_retirada_segundos)
    "params/retencao-inativos-dias"   = tostring(local.neg.retencao_inativos_dias)
    "params/versao-termo-vigente"     = local.neg.versao_termo_vigente
  }
  parametros_sensiveis = {
    "params/administracao-email" = var.admin_email
    "params/alertas-email"       = var.alertas_email
  }
}

resource "aws_ssm_parameter" "params" {
  for_each = local.parametros
  name     = "${local.ssm}/${each.key}"
  type     = "String"
  value    = each.value

  depends_on = [terraform_data.validacoes]
}

# E-mails ficam como String: o runner de migracoes le `params/*` sem decrypt; nao sao segredos.
resource "aws_ssm_parameter" "params_email" {
  for_each = nonsensitive(toset(keys(local.parametros_sensiveis)))
  name     = "${local.ssm}/${each.key}"
  type     = "String"
  value    = local.parametros_sensiveis[each.key]
}

# --- Mensageria, observabilidade e seguranca -----------------------------------
module "messaging" {
  source  = "../../modules/messaging"
  prefixo = local.prefixo
}

module "observability" {
  source                  = "../../modules/observability"
  prefixo                 = local.prefixo
  alertas_email           = var.alertas_email
  retencao_auditoria_dias = local.cfg.observabilidade.retencao_auditoria_dias
}

# --- Dados ---
module "tabela_veiculos" {
  source     = "../../modules/dynamodb_table"
  nome       = "${local.prefixo}-veiculos"
  capacidade = local.capacidade.veiculos

  gsis = {
    gsi_status_preco = {
      hash_key  = "gsi1pk"
      range_key = "gsi1sk"
      rcu       = local.capacidade.veiculos_gsi_status_preco.rcu
      wcu       = local.capacidade.veiculos_gsi_status_preco.wcu
      projecao  = "ALL"
    }
  }
}

module "tabela_clientes" {
  source       = "../../modules/dynamodb_table"
  nome         = "${local.prefixo}-clientes"
  capacidade   = local.capacidade.clientes
  ttl_atributo = "expiraEm"
}

# --- Identidade -----------------------------------------------------------------
module "cognito" {
  source       = "../../modules/cognito"
  prefixo      = local.prefixo
  url_callback = "${module.api.url_base}/docs/oauth2-redirect"
  urls_extras  = ["${module.frontend.url}/auth/callback"]
}

# --- Pacotes e funcoes -----------------------------------------------------------
data "archive_file" "layer" {
  type        = "zip"
  source_dir  = "${local.build_dir}/layer"
  output_path = "${local.build_dir}/layer.zip"
}

resource "aws_lambda_layer_version" "deps" {
  layer_name               = "${local.prefixo}-deps"
  filename                 = data.archive_file.layer.output_path
  source_code_hash         = data.archive_file.layer.output_base64sha256
  compatible_runtimes      = ["python3.13"]
  compatible_architectures = ["arm64"]
}

locals {
  env_comum = {
    SSM_PREFIXO                  = local.ssm
    POWERTOOLS_METRICS_NAMESPACE = "Revenda"
    LOG_LEVEL                    = "INFO"
    VERSAO_APP                   = var.versao_app
  }
  env_auth = {
    POOL_CLIENTES_ID       = module.cognito.pool_clientes_id
    POOL_FUNCIONARIOS_ID   = module.cognito.pool_funcionarios_id
    CLIENT_ID_CLIENTES     = module.cognito.client_id_clientes
    CLIENT_ID_FUNCIONARIOS = module.cognito.client_id_funcionarios
  }
  ssm_arn = "arn:aws:ssm:${local.cfg.regiao}:${local.conta}:parameter${local.ssm}"
  stmt_kms_ssm = {
    Effect   = "Allow"
    Action   = ["kms:Decrypt"]
    Resource = [data.aws_kms_alias.ssm.target_key_arn]
    Condition = {
      StringEquals = { "kms:ViaService" = "ssm.${local.cfg.regiao}.amazonaws.com" }
    }
  }
}

module "pacote_docs" {
  source    = "../../modules/package"
  src_dir   = local.src_dir
  contextos = ["api_docs"]
  saida     = "${local.build_dir}/fn-docs.zip"
  arquivos_extras = {
    "dados/openapi.json" = abspath("${path.root}/../../../../backend/contracts/openapi.json")
  }
}

module "fn_docs" {
  source             = "../../modules/lambda_fn"
  nome               = local.nome_fn_docs
  handler            = "api_docs.adapters.api.handler.handler"
  arquivo_zip        = module.pacote_docs.arquivo
  hash_zip           = module.pacote_docs.hash
  memoria_mb         = 256
  timeout_s          = 5
  layers             = [aws_lambda_layer_version.deps.arn]
  boundary_arn       = local.boundary_arn
  retencao_logs_dias = local.cfg.observabilidade.retencao_logs_dias

  ambiente = merge(local.env_comum, local.env_auth, {
    DOMINIO_CLIENTES     = module.cognito.dominio_clientes
    DOMINIO_FUNCIONARIOS = module.cognito.dominio_funcionarios
  })
}

module "pacote_admin" {
  source    = "../../modules/package"
  src_dir   = local.src_dir
  contextos = ["admin"]
  saida     = "${local.build_dir}/fn-admin-api.zip"
}

module "fn_admin_api" {
  source             = "../../modules/lambda_fn"
  nome               = local.nome_fn_admin
  handler            = "admin.adapters.api.handler.handler"
  arquivo_zip        = module.pacote_admin.arquivo
  hash_zip           = module.pacote_admin.hash
  memoria_mb         = 512
  timeout_s          = 15
  layers             = [aws_lambda_layer_version.deps.arn]
  boundary_arn       = local.boundary_arn
  retencao_logs_dias = local.cfg.observabilidade.retencao_logs_dias

  ambiente = merge(local.env_comum, local.env_auth, {
    TOPICO_EVENTOS_ARN  = module.messaging.topico_eventos_arn
    AUDITORIA_LOG_GROUP = module.observability.log_group_auditoria
    SAGA_ARN            = local.saga_arn
    CLIENTES_TABELA     = module.tabela_clientes.nome
    LGPD_WORKER_FUNCAO  = local.nome_fn_lgpd
  })

  statements = [
    { Effect = "Allow", Action = ["logs:FilterLogEvents"], Resource = ["${module.observability.log_group_auditoria_arn}:*"] },
    { Effect = "Allow", Action = ["states:ListExecutions"], Resource = [local.saga_arn] },
    {
      Effect   = "Allow"
      Action   = ["states:DescribeExecution", "states:RedriveExecution"]
      Resource = ["arn:aws:states:${local.cfg.regiao}:${local.conta}:execution:${local.saga_nome}:*"]
    },
    # Solicitacoes LGPD: Scan somente leitura (operacao administrativa de baixo volume).
    { Effect = "Allow", Action = ["dynamodb:Scan"], Resource = [module.tabela_clientes.arn] },
    # Configuracao inicial: leitura do e-mail do administrador declarado na implantacao.
    { Effect = "Allow", Action = ["ssm:GetParameter"], Resource = ["${local.ssm_arn}/params/administracao-email"] },
    # Rotacoes: PutParameter sem GetParameter nos segredos (a versao anterior fica no historico do SSM).
    {
      Effect = "Allow"
      Action = ["ssm:PutParameter"]
      Resource = [
        "${local.ssm_arn}/segredos/webhook-hmac-atual",
        "${local.ssm_arn}/segredos/pii-chave-privada-*",
        "${local.ssm_arn}/pii/*",
      ]
    },
    { Effect = "Allow", Action = ["ssm:GetParameter"], Resource = ["${local.ssm_arn}/pii/versao-atual"] },
    {
      Effect   = "Allow"
      Action   = ["kms:Encrypt", "kms:GenerateDataKey"]
      Resource = [data.aws_kms_alias.ssm.target_key_arn]
      Condition = {
        StringEquals = { "kms:ViaService" = "ssm.${local.cfg.regiao}.amazonaws.com" }
      }
    },
    { Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = ["arn:aws:lambda:${local.cfg.regiao}:${local.conta}:function:${local.nome_fn_lgpd}"] },
    {
      Effect = "Allow"
      Action = [
        "cognito-idp:AdminCreateUser", "cognito-idp:AdminAddUserToGroup", "cognito-idp:AdminRemoveUserFromGroup",
        "cognito-idp:AdminGetUser", "cognito-idp:AdminListGroupsForUser", "cognito-idp:AdminDisableUser",
        "cognito-idp:AdminEnableUser", "cognito-idp:AdminUserGlobalSignOut", "cognito-idp:ListUsers",
        "cognito-idp:ListUsersInGroup",
      ]
      Resource = [module.cognito.pool_funcionarios_arn]
    },
    {
      Effect   = "Allow"
      Action   = ["ssm:GetParameter"]
      Resource = ["${local.ssm_arn}/segredos/cursor-hmac"]
    },
    local.stmt_kms_ssm,
    {
      Effect   = "Allow"
      Action   = ["sns:Publish"]
      Resource = [module.messaging.topico_eventos_arn]
    },
  ]
}

module "pacote_veiculos" {
  source    = "../../modules/package"
  src_dir   = local.src_dir
  contextos = ["vehicles"]
  saida     = "${local.build_dir}/fn-veiculos-api.zip"
}

module "fn_veiculos_api" {
  source             = "../../modules/lambda_fn"
  nome               = local.nome_fn_veic
  handler            = "vehicles.adapters.api.handler.handler"
  arquivo_zip        = module.pacote_veiculos.arquivo
  hash_zip           = module.pacote_veiculos.hash
  memoria_mb         = local.cfg.lambda.memoria_api_mb
  timeout_s          = 10
  layers             = [aws_lambda_layer_version.deps.arn]
  boundary_arn       = local.boundary_arn
  retencao_logs_dias = local.cfg.observabilidade.retencao_logs_dias

  ambiente = merge(local.env_comum, local.env_auth, {
    VEICULOS_TABELA = module.tabela_veiculos.nome
  })

  statements = [
    {
      Effect = "Allow"
      Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:ConditionCheckItem", "dynamodb:Query"]
      Resource = [
        module.tabela_veiculos.arn,
        "${module.tabela_veiculos.arn}/index/*",
      ]
    },
    {
      Effect   = "Allow"
      Action   = ["ssm:GetParameter"]
      Resource = ["${local.ssm_arn}/segredos/cursor-hmac"]
    },
    local.stmt_kms_ssm,
  ]
}

module "pacote_clientes" {
  source    = "../../modules/package"
  src_dir   = local.src_dir
  contextos = ["customers"]
  saida     = "${local.build_dir}/fn-clientes.zip"
}

module "fn_clientes_api" {
  source             = "../../modules/lambda_fn"
  nome               = local.nome_fn_cli
  handler            = "customers.adapters.api.handler.handler"
  arquivo_zip        = module.pacote_clientes.arquivo
  hash_zip           = module.pacote_clientes.hash
  memoria_mb         = local.cfg.lambda.memoria_api_mb
  timeout_s          = 10
  layers             = [aws_lambda_layer_version.deps.arn]
  boundary_arn       = local.boundary_arn
  retencao_logs_dias = local.cfg.observabilidade.retencao_logs_dias

  ambiente = merge(local.env_comum, local.env_auth, {
    CLIENTES_TABELA         = module.tabela_clientes.nome
    VENDAS_TABELA           = module.tabela_vendas.nome
    TOPICO_EVENTOS_ARN      = module.messaging.topico_eventos_arn
    CLIENTES_INTERNO_FUNCAO = local.nome_fn_cli_i
  })

  # Sem acesso a `segredos/pii-chave-privada-*`: so cifra (chave publica) e calcula HMAC.
  statements = [
    {
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:ConditionCheckItem", "dynamodb:Query"]
      Resource = [module.tabela_clientes.arn]
    },
    # Somente leitura de vendas: lock `RESERVA_ATIVA` e historico do cliente (exportacao/exclusao).
    {
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem", "dynamodb:Query"]
      Resource = [module.tabela_vendas.arn, "${module.tabela_vendas.arn}/index/*"]
    },
    { Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = ["arn:aws:lambda:${local.cfg.regiao}:${local.conta}:function:${local.nome_fn_cli_i}"] },
    { Effect = "Allow", Action = ["cognito-idp:AdminDeleteUser"], Resource = [module.cognito.pool_clientes_arn] },
    {
      Effect = "Allow"
      Action = ["ssm:GetParameter"]
      Resource = [
        "${local.ssm_arn}/pii/versao-atual",
        "${local.ssm_arn}/pii/chave-publica-*",
        "${local.ssm_arn}/segredos/cpf-hmac",
        "${local.ssm_arn}/params/versao-termo-vigente",
      ]
    },
    local.stmt_kms_ssm,
    {
      Effect   = "Allow"
      Action   = ["cognito-idp:AdminGetUser"]
      Resource = [module.cognito.pool_clientes_arn]
    },
    {
      Effect   = "Allow"
      Action   = ["sns:Publish"]
      Resource = [module.messaging.topico_eventos_arn]
    },
  ]
}

module "fn_clientes_interno" {
  source             = "../../modules/lambda_fn"
  nome               = local.nome_fn_cli_i
  handler            = "customers.adapters.internal.handler.handler"
  arquivo_zip        = module.pacote_clientes.arquivo
  hash_zip           = module.pacote_clientes.hash
  memoria_mb         = 512
  timeout_s          = 10
  layers             = [aws_lambda_layer_version.deps.arn]
  boundary_arn       = local.boundary_arn
  retencao_logs_dias = local.cfg.observabilidade.retencao_logs_dias

  ambiente = merge(local.env_comum, { CLIENTES_TABELA = module.tabela_clientes.nome })

  # Unica (com fn-lgpd-worker) com a chave privada PII; sem rota HTTP.
  statements = [
    {
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem"]
      Resource = [module.tabela_clientes.arn]
    },
    {
      Effect   = "Allow"
      Action   = ["ssm:GetParameter"]
      Resource = ["${local.ssm_arn}/segredos/pii-chave-privada-*"]
    },
    {
      Effect   = "Allow"
      Action   = ["ssm:GetParameter"]
      Resource = ["${local.ssm_arn}/params/versao-termo-vigente"]
    },
    {
      Effect   = "Allow"
      Action   = ["kms:Decrypt"]
      Resource = [data.aws_kms_alias.ssm.target_key_arn]
      Condition = {
        StringEquals = { "kms:ViaService" = "ssm.${local.cfg.regiao}.amazonaws.com" }
        ArnLike      = { "kms:EncryptionContext:PARAMETER_ARN" = "${local.ssm_arn}/segredos/pii-chave-privada-*" }
      }
    },
  ]
}

module "pacote_migracoes" {
  source    = "../../modules/package"
  src_dir   = local.src_dir
  contextos = ["migration_runner", "vehicles"]
  saida     = "${local.build_dir}/fn-migracoes.zip"
  arquivos_extras = {
    for f in local.arquivos_migra : "dados/migracoes/${f}" => "${local.migracoes_dir}/${f}"
  }
}

module "fn_migracoes" {
  source             = "../../modules/lambda_fn"
  nome               = "${local.prefixo}-fn-migracoes"
  handler            = "migration_runner.adapters.handler.handler"
  arquivo_zip        = module.pacote_migracoes.arquivo
  hash_zip           = module.pacote_migracoes.hash
  memoria_mb         = 512
  timeout_s          = 300
  layers             = [aws_lambda_layer_version.deps.arn]
  boundary_arn       = local.boundary_arn
  retencao_logs_dias = local.cfg.observabilidade.retencao_logs_dias

  ambiente = merge(local.env_comum, {
    POOL_FUNCIONARIOS_ID = module.cognito.pool_funcionarios_id
    VEICULOS_TABELA      = module.tabela_veiculos.nome
  })

  # Sem GetParameter em segredos/*: a funcao grava segredos, nao os le.
  statements = [
    {
      Effect   = "Allow"
      Action   = ["ssm:PutParameter"]
      Resource = ["${local.ssm_arn}/segredos/*", "${local.ssm_arn}/pii/*", "${local.ssm_arn}/migracoes/*"]
    },
    {
      Effect   = "Allow"
      Action   = ["ssm:GetParameter"]
      Resource = ["${local.ssm_arn}/params/*", "${local.ssm_arn}/migracoes/*", "${local.ssm_arn}/pii/*"]
    },
    {
      Effect   = "Allow"
      Action   = ["kms:Encrypt", "kms:GenerateDataKey"]
      Resource = [data.aws_kms_alias.ssm.target_key_arn]
      Condition = {
        StringEquals = { "kms:ViaService" = "ssm.${local.cfg.regiao}.amazonaws.com" }
      }
    },
    {
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:ConditionCheckItem"]
      Resource = [module.tabela_veiculos.arn]
    },
    {
      Effect   = "Allow"
      Action   = ["cognito-idp:AdminCreateUser", "cognito-idp:AdminAddUserToGroup", "cognito-idp:AdminGetUser"]
      Resource = [module.cognito.pool_funcionarios_arn]
    },
  ]
}

# Impede qualquer principal de ler a chave privada PII, exceto as roles autorizadas.
# As roles de clientes-interno/lgpd-worker sao as unicas que a leem.
# --- API Gateway ----------------------------------------------------------------
module "api" {
  source        = "../../modules/api"
  nome          = "${local.prefixo}-api"
  regiao        = local.cfg.regiao
  provider_arns = [module.cognito.pool_clientes_arn, module.cognito.pool_funcionarios_arn]
  throttling    = local.throttling
  throttling_rotas = {
    "clientes/POST"             = local.throttling.post_clientes_rps
    "configuracao-inicial/POST" = local.throttling.post_clientes_rps
    "vendas/POST"               = local.throttling.post_vendas_rps
    "webhooks/pagamentos/POST"  = local.throttling.webhook_rps
  }

  rotas = {
    "GET /health"                                                   = { lambda_nome = local.nome_fn_docs, acesso = "publico" }
    "GET /docs"                                                     = { lambda_nome = local.nome_fn_docs, acesso = "publico" }
    "GET /docs/openapi.json"                                        = { lambda_nome = local.nome_fn_docs, acesso = "publico" }
    "GET /docs/oauth2-redirect"                                     = { lambda_nome = local.nome_fn_docs, acesso = "publico" }
    "POST /clientes"                                                = { lambda_nome = local.nome_fn_cli, acesso = "cognito" }
    "GET /clientes/meu-perfil"                                      = { lambda_nome = local.nome_fn_cli, acesso = "cognito" }
    "POST /vendas"                                                  = { lambda_nome = local.nome_fn_vendas, acesso = "cognito" }
    "GET /vendas/{venda_id}"                                        = { lambda_nome = local.nome_fn_vendas, acesso = "cognito" }
    "POST /vendas/{venda_id}/desistencia"                           = { lambda_nome = local.nome_fn_vendas, acesso = "cognito" }
    "POST /vendas/{venda_id}/retirada"                              = { lambda_nome = local.nome_fn_vendas, acesso = "cognito" }
    "POST /webhooks/pagamentos"                                     = { lambda_nome = local.nome_fn_webhk, acesso = "publico" }
    "POST /_simulacao/pagamentos/cobrancas"                         = { lambda_nome = local.nome_fn_mock, acesso = "iam" }
    "POST /_simulacao/pagamentos/cobrancas/{transacao_id}/cancelar" = { lambda_nome = local.nome_fn_mock, acesso = "iam" }
    "POST /_simulacao/pagamentos/estornos"                          = { lambda_nome = local.nome_fn_mock, acesso = "iam" }
    "POST /_simulacao/pagamentos/cobrancas/{transacao_id}/simular"  = { lambda_nome = local.nome_fn_mock, acesso = "cognito" }
    "GET /veiculos/vendidos"                                        = { lambda_nome = local.nome_fn_veic, acesso = "cognito" }
    "PATCH /veiculos/{veiculo_id}"                                  = { lambda_nome = local.nome_fn_veic, acesso = "cognito" }
    "POST /veiculos/{veiculo_id}/inativacao"                        = { lambda_nome = local.nome_fn_veic, acesso = "cognito" }
    "POST /veiculos/{veiculo_id}/reativacao"                        = { lambda_nome = local.nome_fn_veic, acesso = "cognito" }
    "GET /gestao/veiculos"                                          = { lambda_nome = local.nome_fn_veic, acesso = "cognito" }
    "GET /gestao/veiculos/{veiculo_id}"                             = { lambda_nome = local.nome_fn_veic, acesso = "cognito" }
    "PATCH /clientes/meu-perfil"                                    = { lambda_nome = local.nome_fn_cli, acesso = "cognito" }
    "POST /clientes/meu-perfil/consentimentos"                      = { lambda_nome = local.nome_fn_cli, acesso = "cognito" }
    "DELETE /clientes/meu-perfil"                                   = { lambda_nome = local.nome_fn_cli, acesso = "cognito" }
    "GET /clientes/meu-perfil/exportacao"                           = { lambda_nome = local.nome_fn_cli, acesso = "cognito" }
    "GET /administracao/auditoria"                                  = { lambda_nome = local.nome_fn_admin, acesso = "cognito" }
    "GET /administracao/solicitacoes-lgpd"                          = { lambda_nome = local.nome_fn_admin, acesso = "cognito" }
    "GET /administracao/sagas"                                      = { lambda_nome = local.nome_fn_admin, acesso = "cognito" }
    "POST /administracao/vendas/{venda_id}/fluxo/reprocessamento"   = { lambda_nome = local.nome_fn_admin, acesso = "cognito" }
    "POST /administracao/segredos/webhook/rotacao"                  = { lambda_nome = local.nome_fn_admin, acesso = "cognito" }
    "POST /administracao/chaves-pii/rotacao"                        = { lambda_nome = local.nome_fn_admin, acesso = "cognito" }
    "GET /clientes/meu-perfil/vendas"                               = { lambda_nome = local.nome_fn_vendas, acesso = "cognito" }
    "GET /vendas"                                                   = { lambda_nome = local.nome_fn_vendas, acesso = "cognito" }
    "GET /vendas/{venda_id}/documentacao"                           = { lambda_nome = local.nome_fn_vendas, acesso = "cognito" }
    "GET /veiculos/vendidos"                                        = { lambda_nome = local.nome_fn_veic, acesso = "cognito" }
    "PATCH /veiculos/{veiculo_id}"                                  = { lambda_nome = local.nome_fn_veic, acesso = "cognito" }
    "POST /veiculos/{veiculo_id}/inativacao"                        = { lambda_nome = local.nome_fn_veic, acesso = "cognito" }
    "POST /veiculos/{veiculo_id}/reativacao"                        = { lambda_nome = local.nome_fn_veic, acesso = "cognito" }
    "GET /gestao/veiculos"                                          = { lambda_nome = local.nome_fn_veic, acesso = "cognito" }
    "GET /gestao/veiculos/{veiculo_id}"                             = { lambda_nome = local.nome_fn_veic, acesso = "cognito" }
    "PATCH /clientes/meu-perfil"                                    = { lambda_nome = local.nome_fn_cli, acesso = "cognito" }
    "POST /clientes/meu-perfil/consentimentos"                      = { lambda_nome = local.nome_fn_cli, acesso = "cognito" }
    "GET /clientes/meu-perfil/vendas"                               = { lambda_nome = local.nome_fn_vendas, acesso = "cognito" }
    "GET /vendas"                                                   = { lambda_nome = local.nome_fn_vendas, acesso = "cognito" }
    "GET /vendas/{venda_id}/documentacao"                           = { lambda_nome = local.nome_fn_vendas, acesso = "cognito" }
    "GET /veiculos"                                                 = { lambda_nome = local.nome_fn_veic, acesso = "publico" }
    "POST /veiculos"                                                = { lambda_nome = local.nome_fn_veic, acesso = "cognito" }
    "GET /veiculos/{veiculo_id}"                                    = { lambda_nome = local.nome_fn_veic, acesso = "publico" }
    "GET /configuracao-inicial"                                     = { lambda_nome = local.nome_fn_admin, acesso = "publico" }
    "POST /configuracao-inicial"                                    = { lambda_nome = local.nome_fn_admin, acesso = "publico" }
    "GET /administracao/funcionarios"                               = { lambda_nome = local.nome_fn_admin, acesso = "cognito" }
    "POST /administracao/funcionarios"                              = { lambda_nome = local.nome_fn_admin, acesso = "cognito" }
    "PATCH /administracao/funcionarios/{funcionario_id}"            = { lambda_nome = local.nome_fn_admin, acesso = "cognito" }
  }
}

# --- Migracoes de dados: depois de pools, parametros e tabelas ------
module "migracoes" {
  source         = "../../modules/migrations"
  funcao_nome    = module.fn_migracoes.nome
  hash_migracoes = local.hash_migracoes
  depende_de = concat(
    [for p in aws_ssm_parameter.params : p.arn],
    [for p in aws_ssm_parameter.params_email : p.arn],
    [module.cognito.pool_funcionarios_id, module.tabela_veiculos.arn],
  )
}

resource "aws_lambda_permission" "api" {
  for_each = {
    docs  = module.fn_docs.nome
    admin = module.fn_admin_api.nome
    veic  = module.fn_veiculos_api.nome
    cli   = module.fn_clientes_api.nome
    vend  = module.fn_vendas_api.nome
    webhk = module.fn_webhook.nome
    mock  = module.fn_gateway_mock.nome
  }

  statement_id  = "AllowApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = each.value
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${module.api.execution_arn}/*/*"
}
