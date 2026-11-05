# Repositorio do projeto e variaveis do Actions.
# Criado aqui (github_criar_repositorio = true) ou reaproveitado, sem ser gerenciado, quando ja existe.
resource "github_repository" "revenda" {
  count = var.github_criar_repositorio ? 1 : 0

  name                   = var.github_repositorio
  visibility             = var.github_visibilidade
  delete_branch_on_merge = true

  lifecycle {
    prevent_destroy = true
    # Depois de criado, a visibilidade passa a ser decisao manual do responsavel.
    ignore_changes = [visibility, security_and_analysis]
  }
}

data "github_repository" "existente" {
  count = var.github_criar_repositorio ? 0 : 1

  name = var.github_repositorio
}

locals {
  repo_nome = one(concat(github_repository.revenda[*].name, data.github_repository.existente[*].name))
  repo_id   = one(concat(github_repository.revenda[*].repo_id, data.github_repository.existente[*].repo_id))
}

resource "github_repository_vulnerability_alerts" "revenda" {
  repository = local.repo_nome
  enabled    = true
}

locals {
  variaveis_actions = {
    AWS_ACCOUNT_ID      = local.conta
    AWS_DEPLOY_ROLE_ARN = aws_iam_role.deploy.arn
    AWS_PLAN_ROLE_ARN   = aws_iam_role.plan.arn
    ADMIN_EMAIL         = var.admin_email
    ALERTAS_EMAIL       = local.alertas_email
    TF_STATE_BUCKET     = aws_s3_bucket.state.bucket
    CONTROLES_AVANCADOS = tostring(var.github_controles_avancados)
  }
}

resource "github_actions_variable" "revenda" {
  for_each      = nonsensitive(toset(keys(local.variaveis_actions)))
  repository    = local.repo_nome
  variable_name = each.key
  value         = local.variaveis_actions[each.key]
}

data "github_user" "responsavel" {
  username = var.github_owner
}

resource "github_repository_environment" "dev" {
  count = var.github_controles_avancados ? 1 : 0

  repository  = local.repo_nome
  environment = "dev"

  # Autoaprovacao permitida: mantenedor unico.
  reviewers {
    users = [data.github_user.responsavel.id]
  }
  prevent_self_review = false
}

resource "github_repository_ruleset" "main" {
  count = var.github_controles_avancados ? 1 : 0

  name        = "protecao-main"
  repository  = local.repo_nome
  target      = "branch"
  enforcement = "active"

  conditions {
    ref_name {
      include = ["~DEFAULT_BRANCH"]
      exclude = []
    }
  }

  rules {
    deletion         = true
    non_fast_forward = true

    pull_request {
      required_approving_review_count = 0
    }

    required_status_checks {
      required_check {
        context = "Qualidade do código"
      }
      required_check {
        context = "Testes do backend"
      }
      required_check {
        context = "Segurança"
      }
    }
  }
}
