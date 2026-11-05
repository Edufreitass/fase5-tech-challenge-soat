output "bucket_state" {
  value = aws_s3_bucket.state.bucket
}

output "role_deploy_arn" {
  value     = aws_iam_role.deploy.arn
  sensitive = true
}

output "boundary_arn" {
  value     = aws_iam_policy.boundary.arn
  sensitive = true
}

output "repositorio_url" {
  description = "URL para o git remote origin."
  value       = "https://github.com/${var.github_owner}/${var.github_repositorio}.git"
}
