# --- LGPD e auditoria ------------------------------------------------------------------------

module "pacote_auditoria" {
  source    = "../../modules/package"
  src_dir   = local.src_dir
  contextos = ["audit"]
  saida     = "${local.build_dir}/fn-auditoria.zip"
}

module "fn_auditoria" {
  source             = "../../modules/lambda_fn"
  nome               = local.nome_fn_audit
  handler            = "audit.adapters.handler.handler"
  arquivo_zip        = module.pacote_auditoria.arquivo
  hash_zip           = module.pacote_auditoria.hash
  memoria_mb         = 256
  timeout_s          = 30
  layers             = [aws_lambda_layer_version.deps.arn]
  boundary_arn       = local.boundary_arn
  retencao_logs_dias = local.cfg.observabilidade.retencao_logs_dias

  ambiente = merge(local.env_comum, { AUDITORIA_LOG_GROUP = module.observability.log_group_auditoria })

  statements = [
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = ["${module.observability.log_group_auditoria_arn}:*"] },
    {
      Effect   = "Allow"
      Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
      Resource = [module.messaging.auditoria_arn]
    },
  ]
}

resource "aws_lambda_event_source_mapping" "auditoria" {
  event_source_arn        = module.messaging.auditoria_arn
  function_name           = module.fn_auditoria.arn
  batch_size              = 10
  function_response_types = ["ReportBatchItemFailures"]
}

# Unica funcao (com fn-clientes-interno) autorizada a ler `segredos/pii-chave-privada-*`.
module "fn_lgpd_worker" {
  source             = "../../modules/lambda_fn"
  nome               = local.nome_fn_lgpd
  handler            = "customers.adapters.data_protection.handler.handler"
  arquivo_zip        = module.pacote_clientes.arquivo
  hash_zip           = module.pacote_clientes.hash
  memoria_mb         = local.cfg.lambda.memoria_worker_mb
  timeout_s          = 300
  layers             = [aws_lambda_layer_version.deps.arn]
  boundary_arn       = local.boundary_arn
  retencao_logs_dias = local.cfg.observabilidade.retencao_logs_dias

  ambiente = merge(local.env_comum, {
    CLIENTES_TABELA  = module.tabela_clientes.nome
    VENDAS_TABELA    = module.tabela_vendas.nome
    POOL_CLIENTES_ID = module.cognito.pool_clientes_id
  })

  statements = [
    {
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:ConditionCheckItem", "dynamodb:Query", "dynamodb:Scan"]
      Resource = [module.tabela_clientes.arn]
    },
    { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:Query"], Resource = [module.tabela_vendas.arn, "${module.tabela_vendas.arn}/index/*"] },
    {
      Effect = "Allow"
      Action = ["ssm:GetParameter"]
      Resource = [
        "${local.ssm_arn}/segredos/pii-chave-privada-*",
        "${local.ssm_arn}/pii/*",
        "${local.ssm_arn}/segredos/cpf-hmac",
        "${local.ssm_arn}/params/retencao-inativos-dias",
      ]
    },
    # Apagar a chave antiga so depois de recifrar tudo.
    { Effect = "Allow", Action = ["ssm:DeleteParameter"], Resource = ["${local.ssm_arn}/segredos/pii-chave-privada-*"] },
    {
      Effect   = "Allow"
      Action   = ["kms:Decrypt"]
      Resource = [data.aws_kms_alias.ssm.target_key_arn]
      Condition = {
        StringEquals = { "kms:ViaService" = "ssm.${local.cfg.regiao}.amazonaws.com" }
      }
    },
    { Effect = "Allow", Action = ["cognito-idp:AdminDeleteUser"], Resource = [module.cognito.pool_clientes_arn] },
  ]
}

# Retencao diaria: clientes sem compra e inativos sao anonimizados.
resource "aws_scheduler_schedule" "retencao_lgpd" {
  name                = "${local.prefixo}-retencao-lgpd"
  schedule_expression = "cron(0 6 * * ? *)"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = module.fn_lgpd_worker.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ acao = "RETENCAO" })
  }

  depends_on = [aws_iam_role_policy.scheduler]
}
