variable "nome" {
  description = "Nome completo da funcao (ex.: revenda-dev-fn-admin-api)."
  type        = string
}

variable "handler" {
  type = string
}

variable "arquivo_zip" {
  type = string
}

variable "hash_zip" {
  type = string
}

variable "memoria_mb" {
  type = number
}

variable "timeout_s" {
  type = number
}

variable "ambiente" {
  type    = map(string)
  default = {}
}

variable "layers" {
  type    = list(string)
  default = []
}

variable "boundary_arn" {
  type = string
}

variable "retencao_logs_dias" {
  type = number
}

variable "xray" {
  type    = bool
  default = true
}

variable "statements" {
  description = "Statements IAM adicionais (lista de objetos Effect/Action/Resource/Condition)."
  type        = any
  default     = []
}

data "aws_iam_policy_document" "confianca" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_cloudwatch_log_group" "fn" {
  name              = "/aws/lambda/${var.nome}"
  retention_in_days = var.retencao_logs_dias
}

resource "aws_iam_role" "fn" {
  name                 = var.nome
  assume_role_policy   = data.aws_iam_policy_document.confianca.json
  permissions_boundary = var.boundary_arn
}

locals {
  base = [
    {
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = ["${aws_cloudwatch_log_group.fn.arn}:*"]
    },
    {
      Effect   = "Allow"
      Action   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
      Resource = ["*"]
    },
  ]
}

resource "aws_iam_role_policy" "fn" {
  name = "permissoes"
  role = aws_iam_role.fn.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = concat(local.base, var.statements)
  })
}

resource "aws_lambda_function" "fn" {
  function_name    = var.nome
  role             = aws_iam_role.fn.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = var.handler
  filename         = var.arquivo_zip
  source_code_hash = var.hash_zip
  memory_size      = var.memoria_mb
  timeout          = var.timeout_s
  layers           = var.layers

  environment {
    variables = var.ambiente
  }

  tracing_config {
    mode = var.xray ? "Active" : "PassThrough"
  }

  logging_config {
    log_format = "JSON"
    log_group  = aws_cloudwatch_log_group.fn.name
  }

  depends_on = [aws_iam_role_policy.fn]
}

output "arn" {
  value = aws_lambda_function.fn.arn
}

output "invoke_arn" {
  value = aws_lambda_function.fn.invoke_arn
}

output "nome" {
  value = aws_lambda_function.fn.function_name
}

output "role_arn" {
  value = aws_iam_role.fn.arn
}
