variable "admin_email" {
  description = "E-mail do administrador inicial: recebe o convite da configuracao inicial (variavel ADMIN_EMAIL do GitHub)."
  type        = string
  sensitive   = true
}

variable "alertas_email" {
  description = "E-mail dos alarmes (variavel ALERTAS_EMAIL do GitHub)."
  type        = string
  sensitive   = true
}

variable "versao_app" {
  description = "Identificador da versao implantada (SHA do commit)."
  type        = string
  default     = "local"
}
