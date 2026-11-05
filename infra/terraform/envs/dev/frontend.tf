# --- Frontend (S3 + CloudFront); os arquivos do build sobem pelo deploy.yml ----------
module "frontend" {
  source    = "../../modules/frontend"
  prefixo   = local.prefixo
  regiao    = local.cfg.regiao
  api_id    = module.api.id
  api_stage = module.api.stage
}

# Configuracao de runtime: so IDs publicos (client IDs e dominios do Cognito), nunca segredos.
resource "aws_s3_object" "frontend_config" {
  bucket       = module.frontend.bucket
  key          = "config.json"
  content_type = "application/json"
  content = jsonencode({
    apiBase      = "/api"
    versaoTermo  = local.neg.versao_termo_vigente
    regiao       = local.cfg.regiao
    clientes     = { clientId = module.cognito.client_id_clientes, dominio = module.cognito.dominio_clientes }
    funcionarios = { clientId = module.cognito.client_id_funcionarios, dominio = module.cognito.dominio_funcionarios }
  })
  cache_control = "no-store"
}
