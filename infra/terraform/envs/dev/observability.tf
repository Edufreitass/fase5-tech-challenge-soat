# --- alarmes (A1-A9), dashboard e amostragem do X-Ray ---------------------------------------
# Limites do free tier: <= 9 alarmes (limite gratuito: 10), 1 dashboard (limite: 3), sem alarme composto.

locals {
  alarme_acoes = [module.observability.topico_alarmes_arn]

  alarmes = {
    "A1-erros-da-api" = {
      descricao = "5XXError da API acima de 1% por 5 min"
      namespace = "AWS/ApiGateway", metrica = "5XXError", estatistica = "Average", periodo = 300, periodos = 1
      limite    = 0.01, dimensoes = { ApiName = module.api.nome, Stage = module.api.stage }
    }
    "A3-erros-de-lambda" = {
      descricao = "Mais de 5 erros de Lambda em 5 min (todas as funcoes)"
      namespace = "AWS/Lambda", metrica = "Errors", estatistica = "Sum", periodo = 300, periodos = 1
      limite    = 5, dimensoes = {}
    }
    "A4-saga-falhou" = {
      descricao = "Execucao da saga com falha (use /administracao/vendas/{id}/fluxo/reprocessamento)"
      namespace = "AWS/States", metrica = "ExecutionsFailed", estatistica = "Sum", periodo = 300, periodos = 1
      limite    = 0, dimensoes = { StateMachineArn = local.saga_arn }
    }
    "A5-dlq-com-mensagens" = {
      descricao = "Mensagens visiveis na DLQ"
      namespace = "AWS/SQS", metrica = "ApproximateNumberOfMessagesVisible", estatistica = "Maximum", periodo = 60, periodos = 1
      limite    = 0, dimensoes = { QueueName = "${local.prefixo}-dlq" }
    }
    "A6-outbox-atrasado" = {
      descricao = "IteratorAge do outbox acima de 60 s"
      namespace = "AWS/Lambda", metrica = "IteratorAge", estatistica = "Maximum", periodo = 60, periodos = 3
      limite    = 60000, dimensoes = { FunctionName = local.nome_fn_outbox }
    }
    "A7-webhook-suspeito" = {
      descricao = "Mais de 5 webhooks suspeitos em 5 min"
      namespace = "Revenda", metrica = "WebhookSuspeito", estatistica = "Sum", periodo = 300, periodos = 1
      limite    = 5, dimensoes = { service = "revenda" }
    }
    "A8-throttling-dynamodb" = {
      descricao = "Throttling persistente do DynamoDB"
      namespace = "Revenda", metrica = "DynamoDBThrottling", estatistica = "Sum", periodo = 60, periodos = 1
      limite    = 0, dimensoes = { service = "revenda" }
    }
    "A9-acesso-anomalo-a-dados-pessoais" = {
      descricao = "Mais de 50 acessos a dados pessoais em 1 h"
      namespace = "Revenda", metrica = "AcessosDadosPessoais", estatistica = "Sum", periodo = 3600, periodos = 1
      limite    = 50, dimensoes = { service = "revenda" }
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "alarmes" {
  for_each = local.alarmes

  alarm_name          = "${local.prefixo}-${each.key}"
  alarm_description   = each.value.descricao
  namespace           = each.value.namespace
  metric_name         = each.value.metrica
  dimensions          = each.value.dimensoes
  statistic           = each.value.estatistica
  period              = each.value.periodo
  evaluation_periods  = each.value.periodos
  threshold           = each.value.limite
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarme_acoes
}

# A2 usa percentil (extended statistic), por isso fica separado.
resource "aws_cloudwatch_metric_alarm" "latencia_api" {
  alarm_name          = "${local.prefixo}-A2-latencia-da-api"
  alarm_description   = "Latency p95 da API acima de 800 ms por 15 min"
  namespace           = "AWS/ApiGateway"
  metric_name         = "Latency"
  dimensions          = { ApiName = module.api.nome, Stage = module.api.stage }
  extended_statistic  = "p95"
  period              = 300
  evaluation_periods  = 3
  threshold           = 800
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarme_acoes
}

locals {
  tabelas_dashboard = [
    module.tabela_veiculos.nome, module.tabela_clientes.nome, module.tabela_vendas.nome,
    module.tabela_pagamentos.nome, module.tabela_idempotencia.nome, module.tabela_gateway_mock.nome,
  ]
  dim_api = ["ApiName", module.api.nome, "Stage", module.api.stage]
  regiao  = local.cfg.regiao

  widgets = [
    { type = "text", x = 0, y = 0, width = 24, height = 1, properties = { markdown = "## API (RED) e latencia - metas: GET /veiculos p95 < 300 ms, POST /vendas p95 < 800 ms" } },
    {
      type = "metric", x = 0, y = 1, width = 8, height = 6
      properties = {
        title = "Requisicoes e erros", region = local.regiao, view = "timeSeries", stat = "Sum", period = 300
        metrics = [
          concat(["AWS/ApiGateway", "Count"], local.dim_api), concat(["AWS/ApiGateway", "4XXError"], local.dim_api),
          concat(["AWS/ApiGateway", "5XXError"], local.dim_api),
        ]
      }
    },
    {
      type = "metric", x = 8, y = 1, width = 8, height = 6
      properties = {
        title = "Latencia (p50 / p95 / p99)", region = local.regiao, view = "timeSeries", period = 300
        metrics = [
          concat(["AWS/ApiGateway", "Latency"], local.dim_api, [{ stat = "p50" }]),
          concat(["AWS/ApiGateway", "Latency"], local.dim_api, [{ stat = "p95" }]),
          concat(["AWS/ApiGateway", "Latency"], local.dim_api, [{ stat = "p99" }]),
          concat(["AWS/ApiGateway", "IntegrationLatency"], local.dim_api, [{ stat = "p95" }]),
        ]
        annotations = { horizontal = [{ label = "A2 (800 ms)", value = 800 }] }
      }
    },
    {
      type = "metric", x = 16, y = 1, width = 8, height = 6
      properties = {
        title = "Lambda: erros, throttles e duracao p95", region = local.regiao, view = "timeSeries", period = 300
        metrics = [
          ["AWS/Lambda", "Errors", { stat = "Sum" }], ["AWS/Lambda", "Throttles", { stat = "Sum" }],
          ["AWS/Lambda", "Duration", { stat = "p95", yAxis = "right" }],
          ["AWS/Lambda", "ConcurrentExecutions", { stat = "Maximum", yAxis = "right" }],
        ]
      }
    },
    { type = "text", x = 0, y = 7, width = 24, height = 1, properties = { markdown = "## Funil de vendas e saga" } },
    {
      type = "metric", x = 0, y = 8, width = 12, height = 6
      properties = {
        title   = "Funil de vendas (metricas de negocio)", region = local.regiao, view = "timeSeries", stat = "Sum", period = 300
        metrics = [for m in ["ReservasCriadas", "ReservasConflito", "VendasConcluidas", "VendasCanceladas", "VendasEstornadas", "PagamentosTardios"] : ["Revenda", m, "service", "revenda"]]
      }
    },
    {
      type = "metric", x = 12, y = 8, width = 12, height = 6
      properties = {
        title   = "Execucoes da saga", region = local.regiao, view = "timeSeries", stat = "Sum", period = 300
        metrics = [for m in ["ExecutionsStarted", "ExecutionsSucceeded", "ExecutionsFailed", "ExecutionsTimedOut"] : ["AWS/States", m, "StateMachineArn", local.saga_arn]]
      }
    },
    { type = "text", x = 0, y = 14, width = 24, height = 1, properties = { markdown = "## Saturacao e seguranca" } },
    {
      type = "metric", x = 0, y = 15, width = 8, height = 6
      properties = {
        title = "DLQ (mensagens visiveis) e IteratorAge do outbox", region = local.regiao, view = "timeSeries", period = 60
        metrics = [
          ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", "${local.prefixo}-dlq", { stat = "Maximum" }],
          ["AWS/Lambda", "IteratorAge", "FunctionName", local.nome_fn_outbox, { stat = "Maximum", yAxis = "right" }],
        ]
      }
    },
    {
      type = "metric", x = 8, y = 15, width = 8, height = 6
      properties = {
        title = "DynamoDB: throttling por tabela", region = local.regiao, view = "timeSeries", stat = "Sum", period = 300
        metrics = concat(
          [for t in local.tabelas_dashboard : ["AWS/DynamoDB", "WriteThrottleEvents", "TableName", t]],
          [for t in local.tabelas_dashboard : ["AWS/DynamoDB", "ReadThrottleEvents", "TableName", t]],
          [["Revenda", "DynamoDBThrottling", "service", "revenda"]],
        )
      }
    },
    {
      type = "metric", x = 16, y = 15, width = 8, height = 6
      properties = {
        title   = "Seguranca: webhook suspeito e acessos a dados pessoais", region = local.regiao, view = "timeSeries", stat = "Sum", period = 300
        metrics = [["Revenda", "WebhookSuspeito", "service", "revenda"], ["Revenda", "AcessosDadosPessoais", "service", "revenda"]]
      }
    },
    {
      type       = "alarm", x = 0, y = 21, width = 24, height = 3
      properties = { title = "Alarmes A1-A9", alarms = concat([for a in aws_cloudwatch_metric_alarm.alarmes : a.arn], [aws_cloudwatch_metric_alarm.latencia_api.arn]) }
    },
  ]
}

resource "aws_cloudwatch_dashboard" "principal" {
  dashboard_name = local.prefixo
  dashboard_body = jsonencode({ widgets = local.widgets })
}

# Amostragem do X-Ray vinda de infra/config/dev.yml (observabilidade.xray_amostragem).
resource "aws_xray_sampling_rule" "revenda" {
  rule_name      = local.prefixo
  priority       = 100
  version        = 1
  reservoir_size = 1
  fixed_rate     = local.cfg.observabilidade.xray_amostragem
  url_path       = "*"
  host           = "*"
  http_method    = "*"
  service_name   = "*"
  service_type   = "*"
  resource_arn   = "*"
}
