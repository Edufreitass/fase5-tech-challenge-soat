# Empacota o codigo de uma funcao (contextos `shared` + os informados) em um zip.
variable "src_dir" {
  type = string
}

variable "contextos" {
  type = list(string)
}

variable "arquivos_extras" {
  description = "Mapa caminho-no-zip => caminho-local (ex.: openapi e migracoes)."
  type        = map(string)
  default     = {}
}

variable "saida" {
  type = string
}

locals {
  arquivos = flatten([
    for ctx in concat(["shared"], var.contextos) : [
      for f in fileset("${var.src_dir}/${ctx}", "**/*.py") : "${ctx}/${f}"
    ]
  ])
}

data "archive_file" "zip" {
  type        = "zip"
  output_path = var.saida

  dynamic "source" {
    for_each = toset(local.arquivos)
    content {
      content  = file("${var.src_dir}/${source.value}")
      filename = source.value
    }
  }

  dynamic "source" {
    for_each = var.arquivos_extras
    content {
      content  = file(source.value)
      filename = source.key
    }
  }
}

output "arquivo" {
  value = data.archive_file.zip.output_path
}

output "hash" {
  value = data.archive_file.zip.output_base64sha256
}
