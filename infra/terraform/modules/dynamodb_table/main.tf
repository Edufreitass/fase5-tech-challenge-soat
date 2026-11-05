variable "nome" {
  type = string
}

variable "hash_key" {
  type    = string
  default = "pk"
}

variable "range_key" {
  description = "null para tabelas so com hash key (ex.: idempotencia do Powertools)."
  type        = string
  default     = "sk"
}

variable "capacidade" {
  description = "{ rcu, wcu } da tabela."
  type        = object({ rcu = number, wcu = number })
}

variable "gsis" {
  description = "GSIs: nome => { hash_key, range_key, rcu, wcu, projecao, atributos }."
  type = map(object({
    hash_key  = string
    range_key = string
    rcu       = number
    wcu       = number
    projecao  = optional(string, "ALL")
    atributos = optional(list(string), [])
  }))
  default = {}
}

variable "ttl_atributo" {
  type    = string
  default = null
}

variable "stream" {
  type    = bool
  default = false
}

locals {
  atributos = toset(compact(concat(
    [var.hash_key, var.range_key],
    [for g in var.gsis : g.hash_key],
    [for g in var.gsis : g.range_key],
  )))
}

# Modo PROVISIONED sem auto scaling, sem PITR e sem backup: free tier.
resource "aws_dynamodb_table" "t" {
  name           = var.nome
  billing_mode   = "PROVISIONED"
  read_capacity  = var.capacidade.rcu
  write_capacity = var.capacidade.wcu

  hash_key  = var.hash_key
  range_key = var.range_key

  deletion_protection_enabled = false
  stream_enabled              = var.stream
  stream_view_type            = var.stream ? "NEW_AND_OLD_IMAGES" : null

  dynamic "attribute" {
    for_each = local.atributos
    content {
      name = attribute.value
      type = "S"
    }
  }

  dynamic "global_secondary_index" {
    for_each = var.gsis
    content {
      name = global_secondary_index.key

      key_schema {
        attribute_name = global_secondary_index.value.hash_key
        key_type       = "HASH"
      }

      key_schema {
        attribute_name = global_secondary_index.value.range_key
        key_type       = "RANGE"
      }

      read_capacity      = global_secondary_index.value.rcu
      write_capacity     = global_secondary_index.value.wcu
      projection_type    = global_secondary_index.value.projecao
      non_key_attributes = global_secondary_index.value.projecao == "INCLUDE" ? global_secondary_index.value.atributos : null
    }
  }

  dynamic "ttl" {
    for_each = var.ttl_atributo == null ? [] : [var.ttl_atributo]
    content {
      attribute_name = ttl.value
      enabled        = true
    }
  }

  server_side_encryption {
    enabled = false
  }
}

output "nome" {
  value = aws_dynamodb_table.t.name
}

output "arn" {
  value = aws_dynamodb_table.t.arn
}

output "stream_arn" {
  value = aws_dynamodb_table.t.stream_arn
}
