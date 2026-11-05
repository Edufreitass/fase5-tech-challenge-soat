# --- saga de compra (vendas, pagamentos, gateway simulado, webhook, state machine) ---------

module "tabela_vendas" {
  source     = "../../modules/dynamodb_table"
  nome       = "${local.prefixo}-vendas"
  capacidade = local.capacidade.vendas
  stream     = true

  gsis = {
    gsi_cliente = {
      hash_key  = "gsi1pk"
      range_key = "gsi1sk"
      rcu       = local.capacidade.vendas_gsi_cliente.rcu
      wcu       = local.capacidade.vendas_gsi_cliente.wcu
    }
    gsi_status = {
      hash_key  = "gsi2pk"
      range_key = "gsi2sk"
      rcu       = local.capacidade.vendas_gsi_status.rcu
      wcu       = local.capacidade.vendas_gsi_status.wcu
    }
  }
}

module "tabela_pagamentos" {
  source     = "../../modules/dynamodb_table"
  nome       = "${local.prefixo}-pagamentos"
  capacidade = local.capacidade.pagamentos
}

# Esquema padrao do Powertools Idempotency: chave `id`, TTL `expiration`.
module "tabela_idempotencia" {
  source       = "../../modules/dynamodb_table"
  nome         = "${local.prefixo}-idempotencia"
  hash_key     = "id"
  range_key    = null
  capacidade   = local.capacidade.idempotencia
  ttl_atributo = "expiration"
}

module "tabela_gateway_mock" {
  source     = "../../modules/dynamodb_table"
  nome       = "${local.prefixo}-gateway-mock"
  hash_key   = "pk"
  range_key  = null
  capacidade = local.capacidade.gateway_mock
}

locals {
  contextos_vendas = ["sales", "vehicles", "payments", "customers"]
  ssm_params_leitura = [
    "${local.ssm_arn}/params/prazo-pagamento-segundos",
    "${local.ssm_arn}/params/prazo-retirada-segundos",
  ]
  env_saga = {
    SAGA_ARN          = local.saga_arn
    VENDAS_TABELA     = module.tabela_vendas.nome
    VEICULOS_TABELA   = module.tabela_veiculos.nome
    PAGAMENTOS_TABELA = module.tabela_pagamentos.nome
  }
  idx_vendas = "${module.tabela_vendas.arn}/index/*"
}

module "pacote_vendas" {
  source    = "../../modules/package"
  src_dir   = local.src_dir
  contextos = local.contextos_vendas
  saida     = "${local.build_dir}/fn-vendas.zip"
}

module "pacote_pagamentos" {
  source    = "../../modules/package"
  src_dir   = local.src_dir
  contextos = ["payments", "customers"]
  saida     = "${local.build_dir}/fn-pagamentos.zip"
}

module "pacote_veiculos_worker" {
  source    = "../../modules/package"
  src_dir   = local.src_dir
  contextos = ["vehicles"]
  saida     = "${local.build_dir}/fn-veiculos-worker.zip"
}

module "pacote_mock" {
  source    = "../../modules/package"
  src_dir   = local.src_dir
  contextos = ["stubs"]
  saida     = "${local.build_dir}/fn-gateway-mock.zip"
}

# --- Lambdas -----------------------------------------------------------------------------------
module "fn_vendas_api" {
  source             = "../../modules/lambda_fn"
  nome               = local.nome_fn_vendas
  handler            = "sales.adapters.api.handler.handler"
  arquivo_zip        = module.pacote_vendas.arquivo
  hash_zip           = module.pacote_vendas.hash
  memoria_mb         = local.cfg.lambda.memoria_api_mb
  timeout_s          = 10
  layers             = [aws_lambda_layer_version.deps.arn]
  boundary_arn       = local.boundary_arn
  retencao_logs_dias = local.cfg.observabilidade.retencao_logs_dias

  ambiente = merge(local.env_comum, local.env_auth, local.env_saga, {
    CLIENTES_INTERNO_FUNCAO = local.nome_fn_cli_i
    TOPICO_EVENTOS_ARN      = module.messaging.topico_eventos_arn
  })

  statements = [
    {
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:ConditionCheckItem", "dynamodb:Query"]
      Resource = [module.tabela_vendas.arn, local.idx_vendas]
    },
    {
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem"]
      Resource = [module.tabela_veiculos.arn, module.tabela_pagamentos.arn]
    },
    # Na reserva so estes atributos do veiculo podem ser alterados; pk/sk sao as chaves (exigidas pelo IAM).
    {
      Effect   = "Allow"
      Action   = ["dynamodb:UpdateItem", "dynamodb:ConditionCheckItem"]
      Resource = [module.tabela_veiculos.arn]
      Condition = {
        "ForAllValues:StringEquals" = { "dynamodb:Attributes" = ["pk", "sk", "status", "versao", "vendaAtualId", "gsi1pk", "atualizadoEm"] }
        "ForAllValues:StringLike"   = { "dynamodb:LeadingKeys" = ["VEICULO#*"] }
      }
    },
    { Effect = "Allow", Action = ["states:SendTaskSuccess", "states:SendTaskFailure"], Resource = ["*"] },
    { Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = ["arn:aws:lambda:${local.cfg.regiao}:${local.conta}:function:${local.nome_fn_cli_i}"] },
    { Effect = "Allow", Action = ["ssm:GetParameter"], Resource = concat(local.ssm_params_leitura, ["${local.ssm_arn}/segredos/cursor-hmac"]) },
    local.stmt_kms_ssm,
    { Effect = "Allow", Action = ["sns:Publish"], Resource = [module.messaging.topico_eventos_arn] },
  ]
}

module "fn_vendas_outbox" {
  source             = "../../modules/lambda_fn"
  nome               = local.nome_fn_outbox
  handler            = "sales.adapters.outbox.handler.handler"
  arquivo_zip        = module.pacote_vendas.arquivo
  hash_zip           = module.pacote_vendas.hash
  memoria_mb         = 256
  timeout_s          = 30
  layers             = [aws_lambda_layer_version.deps.arn]
  boundary_arn       = local.boundary_arn
  retencao_logs_dias = local.cfg.observabilidade.retencao_logs_dias

  ambiente = merge(local.env_comum, local.env_saga)

  statements = [
    { Effect = "Allow", Action = ["dynamodb:UpdateItem"], Resource = [module.tabela_vendas.arn] },
    {
      Effect   = "Allow"
      Action   = ["dynamodb:DescribeStream", "dynamodb:GetRecords", "dynamodb:GetShardIterator", "dynamodb:ListStreams"]
      Resource = [module.tabela_vendas.stream_arn]
    },
    { Effect = "Allow", Action = ["states:StartExecution"], Resource = [local.saga_arn] },
    { Effect = "Allow", Action = ["ssm:GetParameter"], Resource = local.ssm_params_leitura },
    { Effect = "Allow", Action = ["sqs:SendMessage"], Resource = [module.messaging.dlq_arn] },
  ]
}

resource "aws_lambda_event_source_mapping" "outbox" {
  event_source_arn                   = module.tabela_vendas.stream_arn
  function_name                      = module.fn_vendas_outbox.arn
  starting_position                  = "TRIM_HORIZON"
  batch_size                         = 10
  maximum_retry_attempts             = 10
  bisect_batch_on_function_error     = true
  function_response_types            = ["ReportBatchItemFailures"]
  maximum_batching_window_in_seconds = 0

  filter_criteria {
    filter {
      pattern = jsonencode({
        eventName = ["MODIFY"]
        dynamodb = {
          Keys     = { sk = { S = ["META"] } }
          NewImage = { status = { S = ["RESERVADO"] } }
          OldImage = { status = { S = ["CRIADO"] } }
        }
      })
    }
  }

  destination_config {
    on_failure {
      destination_arn = module.messaging.dlq_arn
    }
  }
}

module "fn_vendas_worker" {
  source             = "../../modules/lambda_fn"
  nome               = local.nome_fn_vwork
  handler            = "sales.adapters.saga.handler.handler"
  arquivo_zip        = module.pacote_vendas.arquivo
  hash_zip           = module.pacote_vendas.hash
  memoria_mb         = local.cfg.lambda.memoria_worker_mb
  timeout_s          = 15
  layers             = [aws_lambda_layer_version.deps.arn]
  boundary_arn       = local.boundary_arn
  retencao_logs_dias = local.cfg.observabilidade.retencao_logs_dias

  ambiente = merge(local.env_comum, local.env_saga)

  statements = [
    {
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:ConditionCheckItem", "dynamodb:Query"]
      Resource = [module.tabela_vendas.arn, local.idx_vendas]
    },
    # REGISTRAR_TOKEN guarda o token tambem no pagamento (usado pelo webhook).
    { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:UpdateItem"], Resource = [module.tabela_pagamentos.arn] },
    { Effect = "Allow", Action = ["states:SendTaskSuccess", "states:SendTaskFailure"], Resource = ["*"] },
    { Effect = "Allow", Action = ["states:StartExecution"], Resource = [local.saga_arn] },
    { Effect = "Allow", Action = ["ssm:GetParameter"], Resource = local.ssm_params_leitura },
  ]
}

module "fn_veiculos_worker" {
  source             = "../../modules/lambda_fn"
  nome               = local.nome_fn_veiwk
  handler            = "vehicles.adapters.saga.handler.handler"
  arquivo_zip        = module.pacote_veiculos_worker.arquivo
  hash_zip           = module.pacote_veiculos_worker.hash
  memoria_mb         = local.cfg.lambda.memoria_worker_mb
  timeout_s          = 15
  layers             = [aws_lambda_layer_version.deps.arn]
  boundary_arn       = local.boundary_arn
  retencao_logs_dias = local.cfg.observabilidade.retencao_logs_dias

  ambiente = merge(local.env_comum, { VEICULOS_TABELA = module.tabela_veiculos.nome })

  statements = [
    { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:UpdateItem"], Resource = [module.tabela_veiculos.arn] },
  ]
}

module "fn_pagamentos_worker" {
  source             = "../../modules/lambda_fn"
  nome               = local.nome_fn_pagwk
  handler            = "payments.adapters.saga.handler.handler"
  arquivo_zip        = module.pacote_pagamentos.arquivo
  hash_zip           = module.pacote_pagamentos.hash
  memoria_mb         = local.cfg.lambda.memoria_worker_mb
  timeout_s          = 15
  layers             = [aws_lambda_layer_version.deps.arn]
  boundary_arn       = local.boundary_arn
  retencao_logs_dias = local.cfg.observabilidade.retencao_logs_dias

  ambiente = merge(local.env_comum, {
    PAGAMENTOS_TABELA       = module.tabela_pagamentos.nome
    GATEWAY_URL             = module.api.url_base
    CLIENTES_INTERNO_FUNCAO = local.nome_fn_cli_i
  })

  statements = [
    {
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:ConditionCheckItem"]
      Resource = [module.tabela_pagamentos.arn]
    },
    { Effect = "Allow", Action = ["execute-api:Invoke"], Resource = ["${module.api.execution_arn}/*/POST/_simulacao/pagamentos/*"] },
    { Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = ["arn:aws:lambda:${local.cfg.regiao}:${local.conta}:function:${local.nome_fn_cli_i}"] },
  ]
}

module "fn_webhook" {
  source             = "../../modules/lambda_fn"
  nome               = local.nome_fn_webhk
  handler            = "payments.adapters.webhook.handler.handler"
  arquivo_zip        = module.pacote_pagamentos.arquivo
  hash_zip           = module.pacote_pagamentos.hash
  memoria_mb         = 512
  timeout_s          = 10
  layers             = [aws_lambda_layer_version.deps.arn]
  boundary_arn       = local.boundary_arn
  retencao_logs_dias = local.cfg.observabilidade.retencao_logs_dias

  ambiente = merge(local.env_comum, {
    PAGAMENTOS_TABELA        = module.tabela_pagamentos.nome
    IDEMPOTENCIA_TABELA      = module.tabela_idempotencia.nome
    PAGAMENTOS_WORKER_FUNCAO = local.nome_fn_pagwk
  })

  statements = [
    { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:UpdateItem"], Resource = [module.tabela_pagamentos.arn] },
    {
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"]
      Resource = [module.tabela_idempotencia.arn]
    },
    {
      Effect   = "Allow"
      Action   = ["ssm:GetParameter"]
      Resource = ["${local.ssm_arn}/segredos/webhook-hmac-atual", "${local.ssm_arn}/segredos/webhook-hmac-anterior"]
    },
    local.stmt_kms_ssm,
    { Effect = "Allow", Action = ["states:SendTaskSuccess", "states:SendTaskFailure"], Resource = ["*"] },
    { Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = ["arn:aws:lambda:${local.cfg.regiao}:${local.conta}:function:${local.nome_fn_pagwk}"] },
  ]
}

module "fn_gateway_mock" {
  source             = "../../modules/lambda_fn"
  nome               = local.nome_fn_mock
  handler            = "stubs.mock_gateway.adapters.api.handler.handler"
  arquivo_zip        = module.pacote_mock.arquivo
  hash_zip           = module.pacote_mock.hash
  memoria_mb         = 256
  timeout_s          = 30
  layers             = [aws_lambda_layer_version.deps.arn]
  boundary_arn       = local.boundary_arn
  retencao_logs_dias = local.cfg.observabilidade.retencao_logs_dias

  ambiente = merge(local.env_comum, local.env_auth, {
    GATEWAY_MOCK_TABELA = module.tabela_gateway_mock.nome
    MOCK_WEBHOOKS_URL   = module.messaging.mock_webhooks_url
    WEBHOOK_URL         = "${module.api.url_base}/webhooks/pagamentos"
  })

  statements = [
    { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"], Resource = [module.tabela_gateway_mock.arn] },
    {
      Effect   = "Allow"
      Action   = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
      Resource = [module.messaging.mock_webhooks_arn]
    },
    { Effect = "Allow", Action = ["ssm:GetParameter"], Resource = ["${local.ssm_arn}/segredos/webhook-hmac-atual"] },
    local.stmt_kms_ssm,
  ]
}

resource "aws_lambda_event_source_mapping" "mock_webhooks" {
  event_source_arn        = module.messaging.mock_webhooks_arn
  function_name           = module.fn_gateway_mock.arn
  batch_size              = 10
  function_response_types = ["ReportBatchItemFailures"]
}

# --- State machine -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "saga" {
  name              = "/aws/vendedlogs/states/${local.saga_nome}"
  retention_in_days = local.cfg.observabilidade.retencao_logs_dias
}

data "aws_iam_policy_document" "saga_confianca" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "saga" {
  name                 = "${local.prefixo}-saga"
  assume_role_policy   = data.aws_iam_policy_document.saga_confianca.json
  permissions_boundary = local.boundary_arn
}

resource "aws_iam_role_policy" "saga" {
  name = "permissoes"
  role = aws_iam_role.saga.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = flatten([for f in [module.fn_vendas_worker, module.fn_veiculos_worker, module.fn_pagamentos_worker] : [f.arn, "${f.arn}:*"]])
      },
      { Effect = "Allow", Action = ["sns:Publish"], Resource = [module.messaging.topico_eventos_arn] },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery", "logs:GetLogDelivery", "logs:UpdateLogDelivery", "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries", "logs:PutResourcePolicy", "logs:DescribeResourcePolicies", "logs:DescribeLogGroups",
        ]
        Resource = ["*"]
      },
      { Effect = "Allow", Action = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"], Resource = ["*"] },
    ]
  })
}

resource "aws_sfn_state_machine" "saga" {
  name     = local.saga_nome
  role_arn = aws_iam_role.saga.arn
  type     = "STANDARD"

  definition = templatefile("${path.root}/../../../../infra/workflows/purchase_saga.asl.json", {
    fn_vendas_worker_arn     = module.fn_vendas_worker.arn
    fn_veiculos_worker_arn   = module.fn_veiculos_worker.arn
    fn_pagamentos_worker_arn = module.fn_pagamentos_worker.arn
    topico_eventos_arn       = module.messaging.topico_eventos_arn
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.saga.arn}:*"
    include_execution_data = false # input/output so tem IDs, mas nunca logamos dados da execucao
    level                  = "ERROR"
  }

  tracing_configuration {
    enabled = true
  }

  depends_on = [aws_iam_role_policy.saga]
}

# --- Varredura de vendas orfas (15 em 15 minutos) --------------------------------------------------
data "aws_iam_policy_document" "scheduler_confianca" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name                 = "${local.prefixo}-scheduler"
  assume_role_policy   = data.aws_iam_policy_document.scheduler_confianca.json
  permissions_boundary = local.boundary_arn
}

resource "aws_iam_role_policy" "scheduler" {
  name = "invocar-worker"
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = [module.fn_vendas_worker.arn, module.fn_lgpd_worker.arn] }]
  })
}

resource "aws_scheduler_schedule" "varredura" {
  name                = "${local.prefixo}-varredura-vendas"
  schedule_expression = "rate(15 minutes)"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = module.fn_vendas_worker.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ acao = "VARREDURA" })
  }

  depends_on = [aws_iam_role_policy.scheduler]
}
