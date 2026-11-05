variable "prefixo" {
  type = string
}

variable "alertas_email" {
  type      = string
  sensitive = true
}

variable "retencao_auditoria_dias" {
  type = number
}

resource "aws_sns_topic" "alarmes" {
  name = "${var.prefixo}-alarmes"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alarmes.arn
  protocol  = "email"
  endpoint  = var.alertas_email
}

# Trilha de auditoria (escrita por fn-auditoria): retencao de 5 anos.
resource "aws_cloudwatch_log_group" "auditoria" {
  name              = "/revenda/dev/auditoria"
  retention_in_days = var.retencao_auditoria_dias
}

output "topico_alarmes_arn" {
  value = aws_sns_topic.alarmes.arn
}

output "log_group_auditoria" {
  value = aws_cloudwatch_log_group.auditoria.name
}

output "log_group_auditoria_arn" {
  value = aws_cloudwatch_log_group.auditoria.arn
}
