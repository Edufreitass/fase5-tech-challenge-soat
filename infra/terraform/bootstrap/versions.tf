terraform {
  required_version = "~> 1.16"

  # Estado local (terraform.tfstate, fora do Git): o bucket de estado do ambiente e criado por este modulo.
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    github = {
      source  = "integrations/github"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region  = local.cfg.regiao
  profile = var.aws_profile

  default_tags {
    tags = { projeto = "revenda", ambiente = "dev", gerenciado-por = "terraform-bootstrap" }
  }
}

provider "github" {
  owner = var.github_owner
  token = var.github_token
}
