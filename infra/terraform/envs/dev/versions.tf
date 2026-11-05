terraform {
  required_version = "~> 1.16"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.12"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # O bucket vem de -backend-config="bucket=$TF_STATE_BUCKET" (variavel do GitHub, nao versionada).
  backend "s3" {
    key          = "envs/dev/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region = local.cfg.regiao

  default_tags {
    tags = { projeto = "revenda", ambiente = local.cfg.ambiente, gerenciado-por = "terraform" }
  }
}
