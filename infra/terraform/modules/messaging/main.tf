variable "prefixo" {
  type = string
}

resource "aws_sns_topic" "eventos" {
  name = "${var.prefixo}-eventos"
}

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.prefixo}-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

# Webhooks do gateway simulado (DelaySeconds para simular atraso); falhas -> DLQ apos 5 tentativas.
resource "aws_sqs_queue" "mock_webhooks" {
  name                       = "${var.prefixo}-mock-webhooks"
  visibility_timeout_seconds = 180
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 5
  })
}

# Trilha de auditoria: SNS -> SQS (entrega bruta) -> fn-auditoria -> log group; 5 tentativas e DLQ.
resource "aws_sqs_queue" "auditoria" {
  name                       = "${var.prefixo}-auditoria"
  visibility_timeout_seconds = 180
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 5
  })
}

data "aws_iam_policy_document" "auditoria" {
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.auditoria.arn]
    principals {
      type        = "Service"
      identifiers = ["sns.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_sns_topic.eventos.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "auditoria" {
  queue_url = aws_sqs_queue.auditoria.id
  policy    = data.aws_iam_policy_document.auditoria.json
}

resource "aws_sns_topic_subscription" "auditoria" {
  topic_arn            = aws_sns_topic.eventos.arn
  protocol             = "sqs"
  endpoint             = aws_sqs_queue.auditoria.arn
  raw_message_delivery = true

  depends_on = [aws_sqs_queue_policy.auditoria]
}

output "auditoria_arn" {
  value = aws_sqs_queue.auditoria.arn
}

output "topico_eventos_arn" {
  value = aws_sns_topic.eventos.arn
}

output "dlq_arn" {
  value = aws_sqs_queue.dlq.arn
}

output "mock_webhooks_arn" {
  value = aws_sqs_queue.mock_webhooks.arn
}

output "mock_webhooks_url" {
  value = aws_sqs_queue.mock_webhooks.url
}
