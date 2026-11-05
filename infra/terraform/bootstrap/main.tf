locals {
  cfg     = yamldecode(file("${path.module}/../../config/dev.yml"))
  prefixo = "revenda-${local.cfg.ambiente}"
  conta   = data.aws_caller_identity.atual.account_id
  bucket  = "${local.prefixo}-tfstate-${local.conta}"
  # O `sub` do token OIDC usa a caixa exata do GitHub; a trust policy compara com StringEquals (diferencia maiusculas).
  owner         = data.github_user.responsavel.login
  repo_oidc     = "${local.owner}/${local.repo_nome}"
  boundary_nm   = "${local.prefixo}-boundary"
  alertas_email = coalesce(var.alertas_email, var.admin_email)

  # Repositorios novos usam o `sub` imutavel (com IDs numericos); aceita tambem o formato classico.
  repo_oidc_subs = [
    "repo:${local.repo_oidc}",
    "repo:${local.owner}@${data.github_user.responsavel.id}/${local.repo_nome}@${local.repo_id}",
  ]
}

data "aws_caller_identity" "atual" {}

# --- State remoto -------------------------------------------------------------
resource "aws_s3_bucket" "state" {
  bucket        = local.bucket
  force_destroy = false
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    id     = "expirar-versoes-antigas"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "state_somente_tls" {
  statement {
    sid       = "NegarSemTLS"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = data.aws_iam_policy_document.state_somente_tls.json
}

# --- Orcamento "zero spend" ---------------------------------------------
resource "aws_budgets_budget" "zero" {
  name         = "${local.prefixo}-zero-spend"
  budget_type  = "COST"
  limit_amount = "0.01"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [local.alertas_email]
  }
}
