variable "prefixo" {
  type = string
}

variable "url_callback" {
  description = "URL de retorno do Swagger UI (/docs/oauth2-redirect)."
  type        = string
}

variable "urls_extras" {
  description = "URLs de retorno adicionais (frontend)."
  type        = list(string)
  default     = []
}

resource "random_string" "dominio" {
  length  = 6
  upper   = false
  special = false
}

locals {
  senha = {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }
}

# --- Pool de clientes (auto-cadastro, MFA opcional) -----------------------------
resource "aws_cognito_user_pool" "clientes" {
  name                     = "${var.prefixo}-clientes"
  user_pool_tier           = "ESSENTIALS"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = "OPTIONAL"
  deletion_protection      = "INACTIVE"

  password_policy {
    minimum_length    = local.senha.minimum_length
    require_lowercase = local.senha.require_lowercase
    require_uppercase = local.senha.require_uppercase
    require_numbers   = local.senha.require_numbers
    require_symbols   = local.senha.require_symbols
  }

  software_token_mfa_configuration {
    enabled = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  admin_create_user_config {
    allow_admin_create_user_only = false
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true
    string_attribute_constraints {
      min_length = 5
      max_length = 254
    }
  }
}

resource "aws_cognito_user_pool_domain" "clientes" {
  domain       = "${var.prefixo}-clientes-${random_string.dominio.result}"
  user_pool_id = aws_cognito_user_pool.clientes.id
}

resource "aws_cognito_user_pool_client" "clientes" {
  name         = "swagger-clientes"
  user_pool_id = aws_cognito_user_pool.clientes.id

  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = concat([var.url_callback], var.urls_extras)
  logout_urls                          = concat([var.url_callback], var.urls_extras)
  # USER_PASSWORD_AUTH: login da tela propria do frontend (TLS ate o Cognito; senha nunca passa pela API).
  # ADMIN_USER_PASSWORD_AUTH exige credenciais IAM (nao e login publico): usado por E2E e carga.
  explicit_auth_flows           = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_ADMIN_USER_PASSWORD_AUTH"]
  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 30
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}

# --- Pool de funcionarios (so convite, MFA TOTP obrigatorio) --------------------
resource "aws_cognito_user_pool" "funcionarios" {
  name                     = "${var.prefixo}-funcionarios"
  user_pool_tier           = "ESSENTIALS"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = "ON"
  deletion_protection      = "INACTIVE"

  password_policy {
    minimum_length                   = local.senha.minimum_length
    require_lowercase                = local.senha.require_lowercase
    require_uppercase                = local.senha.require_uppercase
    require_numbers                  = local.senha.require_numbers
    require_symbols                  = local.senha.require_symbols
    temporary_password_validity_days = 7
  }

  software_token_mfa_configuration {
    enabled = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  schema {
    name                = "name"
    attribute_data_type = "String"
    required            = false
    mutable             = true
    string_attribute_constraints {
      min_length = 1
      max_length = 120
    }
  }
}

resource "aws_cognito_user_group" "admin" {
  name         = "admin"
  user_pool_id = aws_cognito_user_pool.funcionarios.id
  description  = "Administradores"
}

resource "aws_cognito_user_group" "vendedor" {
  name         = "vendedor"
  user_pool_id = aws_cognito_user_pool.funcionarios.id
  description  = "Vendedores/operadores"
}

resource "aws_cognito_user_pool_domain" "funcionarios" {
  domain       = "${var.prefixo}-func-${random_string.dominio.result}"
  user_pool_id = aws_cognito_user_pool.funcionarios.id
}

resource "aws_cognito_user_pool_client" "funcionarios" {
  name         = "swagger-funcionarios"
  user_pool_id = aws_cognito_user_pool.funcionarios.id

  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = concat([var.url_callback], var.urls_extras)
  logout_urls                          = concat([var.url_callback], var.urls_extras)
  explicit_auth_flows                  = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  prevent_user_existence_errors        = "ENABLED"
  enable_token_revocation              = true

  access_token_validity  = 15
  id_token_validity      = 15
  refresh_token_validity = 8
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "hours"
  }
}

output "pool_clientes_id" {
  value = aws_cognito_user_pool.clientes.id
}

output "pool_clientes_arn" {
  value = aws_cognito_user_pool.clientes.arn
}

output "pool_funcionarios_id" {
  value = aws_cognito_user_pool.funcionarios.id
}

output "pool_funcionarios_arn" {
  value = aws_cognito_user_pool.funcionarios.arn
}

output "client_id_clientes" {
  value = aws_cognito_user_pool_client.clientes.id
}

output "client_id_funcionarios" {
  value = aws_cognito_user_pool_client.funcionarios.id
}

output "dominio_clientes" {
  value = aws_cognito_user_pool_domain.clientes.domain
}

output "dominio_funcionarios" {
  value = aws_cognito_user_pool_domain.funcionarios.domain
}
