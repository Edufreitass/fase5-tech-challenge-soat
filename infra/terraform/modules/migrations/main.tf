variable "funcao_nome" {
  type = string
}

variable "hash_migracoes" {
  description = "Hash do diretorio backend/data_migrations/: reinvoca o runner quando mudar."
  type        = string
}

variable "depende_de" {
  description = "Recursos que precisam existir antes (parametros, pools, tabelas)."
  type        = list(string)
  default     = []
}

# A role/politica recem-criada da funcao pode demorar a propagar no IAM (consistencia eventual):
# sem a espera, a primeira invocacao apos uma recriacao falhava com AccessDenied.
resource "time_sleep" "propagacao_iam" {
  create_duration = "30s"

  triggers = {
    funcao = var.funcao_nome
    deps   = join(",", var.depende_de)
  }
}

# Falha da invocacao (FunctionError) falha o deploy. Retorno: so versoes e duracao.
resource "aws_lambda_invocation" "migracoes" {
  depends_on    = [time_sleep.propagacao_iam]
  function_name = var.funcao_nome
  input         = jsonencode({ hash = var.hash_migracoes })

  triggers = {
    hash = var.hash_migracoes
    deps = join(",", var.depende_de)
  }
}

output "resultado" {
  value = jsondecode(aws_lambda_invocation.migracoes.result)
}
