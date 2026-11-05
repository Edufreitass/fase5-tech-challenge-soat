# Unica fonte de configuracao do ambiente; sem *.tfvars.
locals {
  cfg     = yamldecode(file("${path.root}/../../../../infra/config/dev.yml"))
  prefixo = "revenda-${local.cfg.ambiente}"
  ssm     = "/revenda/${local.cfg.ambiente}"
  conta   = data.aws_caller_identity.atual.account_id

  capacidade     = local.cfg.dynamodb_capacidade
  rcu_total      = sum([for c in values(local.capacidade) : c.rcu])
  wcu_total      = sum([for c in values(local.capacidade) : c.wcu])
  throttling     = local.cfg.api.throttling
  neg            = local.cfg.negocio
  src_dir        = abspath("${path.root}/../../../../backend/src")
  build_dir      = abspath("${path.root}/../../../../build")
  migracoes_dir  = abspath("${path.root}/../../../../backend/data_migrations")
  boundary_arn   = "arn:aws:iam::${local.conta}:policy/${local.prefixo}-boundary"
  nome_fn_docs   = "${local.prefixo}-fn-docs"
  nome_fn_admin  = "${local.prefixo}-fn-admin-api"
  nome_fn_veic   = "${local.prefixo}-fn-veiculos-api"
  nome_fn_cli    = "${local.prefixo}-fn-clientes-api"
  nome_fn_cli_i  = "${local.prefixo}-fn-clientes-interno"
  nome_fn_vendas = "${local.prefixo}-fn-vendas-api"
  nome_fn_outbox = "${local.prefixo}-fn-vendas-outbox"
  nome_fn_vwork  = "${local.prefixo}-fn-vendas-worker"
  nome_fn_veiwk  = "${local.prefixo}-fn-veiculos-worker"
  nome_fn_pagwk  = "${local.prefixo}-fn-pagamentos-worker"
  nome_fn_webhk  = "${local.prefixo}-fn-webhook-pagamentos"
  nome_fn_mock   = "${local.prefixo}-fn-gateway-mock"
  nome_fn_audit  = "${local.prefixo}-fn-auditoria"
  nome_fn_lgpd   = "${local.prefixo}-fn-lgpd-worker"
  # ARN estatico da saga: as Lambdas o recebem por ambiente e a state machine referencia as Lambdas.
  saga_nome      = "${local.prefixo}-saga-compra"
  saga_arn       = "arn:aws:states:${local.cfg.regiao}:${local.conta}:stateMachine:${local.prefixo}-saga-compra"
  kms_ssm_alias  = "alias/aws/ssm"
  arquivos_migra = fileset(local.migracoes_dir, "V*.yml")
  hash_migracoes = sha256(join("", [for f in sort(local.arquivos_migra) : filesha256("${local.migracoes_dir}/${f}")]))
}

data "aws_caller_identity" "atual" {}

data "aws_kms_alias" "ssm" {
  name = local.kms_ssm_alias
}

# Validacoes (alem do schema JSON verificado no CI).
resource "terraform_data" "validacoes" {
  lifecycle {
    precondition {
      condition     = local.cfg.regiao == "us-east-1"
      error_message = "Somente us-east-1 e suportada."
    }
    precondition {
      condition     = can(tobool(local.cfg.destroy))
      error_message = "destroy deve ser booleano."
    }
    precondition {
      condition     = local.rcu_total <= 25 && local.wcu_total <= 25
      error_message = "Capacidade DynamoDB acima do free tier (max. 25 RCU e 25 WCU somados)."
    }
    precondition {
      condition     = alltrue([for c in values(local.capacidade) : c.rcu >= 1 && c.wcu >= 1])
      error_message = "Cada capacidade DynamoDB deve ser >= 1."
    }
    precondition {
      condition     = alltrue([for v in values(local.throttling) : v > 0]) && local.throttling.stage_rps <= 10000 && local.throttling.stage_burst <= 5000
      error_message = "Throttling deve ser > 0 e dentro dos limites do stage."
    }
    precondition {
      condition     = alltrue([for o in local.cfg.api.cors_origens : startswith(o, "https://") && !strcontains(o, "*")])
      error_message = "cors_origens: somente https:// e sem curinga."
    }
    precondition {
      condition = alltrue([
        for p in [local.neg.prazo_pagamento_segundos, local.neg.prazo_retirada_segundos] : p >= 60 && p <= 2592000
      ])
      error_message = "Prazos de negocio devem estar entre 60 s e 30 dias."
    }
  }
}
