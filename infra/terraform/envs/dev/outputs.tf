output "api_url" {
  description = "URL base da API (stage v1)."
  value       = module.api.url_base
}

output "swagger_url" {
  value = "${module.api.url_base}/docs"
}

output "client_id_clientes" {
  value = module.cognito.client_id_clientes
}

output "client_id_funcionarios" {
  value = module.cognito.client_id_funcionarios
}

output "migracoes_aplicadas" {
  value = module.migracoes.resultado
}

output "frontend_url" {
  value = module.frontend.url
}

output "frontend_bucket" {
  value = module.frontend.bucket
}

output "frontend_distribuicao_id" {
  value = module.frontend.distribuicao_id
}
