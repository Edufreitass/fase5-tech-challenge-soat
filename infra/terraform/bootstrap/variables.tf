variable "admin_email" {
  description = "E-mail do primeiro administrador: recebe o convite da configuracao inicial."
  type        = string
  sensitive   = true

  validation {
    condition     = !endswith(var.admin_email, "@exemplo.com")
    error_message = "Troque os valores de exemplo em terraform.tfvars pelos seus."
  }
}

variable "alertas_email" {
  description = "E-mail dos alarmes e do alerta de orcamento. Sem valor, usa admin_email."
  type        = string
  default     = null
  sensitive   = true

  validation {
    condition     = var.alertas_email == null || !endswith(coalesce(var.alertas_email, ""), "@exemplo.com")
    error_message = "Troque os valores de exemplo em terraform.tfvars pelos seus."
  }
}

variable "aws_profile" {
  description = "Perfil do AWS CLI a usar. Sem valor, vale a configuracao padrao do AWS CLI."
  type        = string
  default     = null
}

variable "github_token" {
  description = "Token do GitHub (resultado de `gh auth token`). Sem valor, usa a variavel de ambiente GITHUB_TOKEN."
  type        = string
  default     = null
  sensitive   = true
}

variable "github_owner" {
  description = "Usuario do GitHub dono do repositorio."
  type        = string
}

variable "github_repositorio" {
  description = "Nome do repositorio do projeto."
  type        = string
}

variable "github_criar_repositorio" {
  description = "true cria o repositorio (ele nao pode existir); false usa um repositorio que ja existe."
  type        = bool
  default     = true
}

variable "github_visibilidade" {
  description = "Visibilidade do repositorio criado (private ou public). Ignorada quando ele ja existe."
  type        = string
  default     = "private"

  validation {
    condition     = contains(["private", "public"], var.github_visibilidade)
    error_message = "github_visibilidade deve ser private ou public."
  }
}

variable "github_controles_avancados" {
  description = "Cria environment com reviewer e ruleset da main. Exige repositorio publico (GitHub Free). Padrao: false enquanto privado."
  type        = bool
  default     = false
}
