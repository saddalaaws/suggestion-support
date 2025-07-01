terraform {
  required_providers {
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2.0"
    }
    external = {
      source  = "hashicorp/external"
      version = "~> 2.3.0"
    }
    aws = {
      source                = "hashicorp/aws"
      configuration_aliases = [aws.main, aws.backup, aws.global]
      version               = "~> 5.90"
    }
    grafana = {
      source  = "grafana/grafana"
      version = "~> 3.22.0"
    }
  }
  required_version = "= 1.11.1"
}
