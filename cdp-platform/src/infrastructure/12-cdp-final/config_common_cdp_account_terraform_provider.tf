################################################################################
# DevOps Provider configuration
#-------------------------------------------------------------------------------

variable "AWS_DEVOPS_REGION" {
  description = "AWS DevOps region"
  type        = string
}

variable "LOCAL_AWS_DEVOPS_PROFILE" {
  description = "Name of the local AWS DevOps profile"
  type        = string
  default     = null
}

module "devops_provider_setup" {
  source = "../../../../terraform-modules/provider_setup/devops"
  deployed_by = {
    pipeline   = "devops-pipeline-cdp-deploy-platform"
    repository = "cdp-platform"
  }
}

provider "aws" {
  alias   = "devops"
  region  = var.AWS_DEVOPS_REGION
  profile = var.LOCAL_AWS_DEVOPS_PROFILE
  default_tags { tags = module.devops_provider_setup.devops_default_tags }
}


################################################################################
# Deployment setup
#-------------------------------------------------------------------------------

variable "AWS_DEPLOY_PARAMETERS_PATH" {
  description = "Path to the SSM parameter with the deployment settings"
  type        = string
}

variable "LOCAL_AWS_DEPLOY_PROFILE" {
  description = "Name of the AWS deployment profile"
  type        = string
  default     = null
}

variable "LOCAL_AWS_DEPLOY_PROFILE_OVERRIDE" {
  description = "Name of the AWS deployment profile to override the configured one"
  type        = string
  default     = null
}

variable "LOCAL_AWS_DEPLOY_FORCE_ROLE" {
  description = "Force usage of the deployment role"
  type        = bool
  default     = false
}

module "deploy_provider_setup" {
  source                  = "../../../../terraform-modules/provider_setup/deploy"
  deployed_by             = module.devops_provider_setup.deployed_by
  deploy_parameters_path  = var.AWS_DEPLOY_PARAMETERS_PATH
  deploy_module           = "deploy"
  deploy_profile          = var.LOCAL_AWS_DEPLOY_PROFILE
  deploy_profile_override = var.LOCAL_AWS_DEPLOY_PROFILE_OVERRIDE
  deploy_force_role       = var.LOCAL_AWS_DEPLOY_FORCE_ROLE
  providers               = { aws = aws.devops }
}

provider "aws" {
  region  = module.deploy_provider_setup.deploy_settings.region
  profile = module.deploy_provider_setup.deploy_settings.deploy_profile
  default_tags { tags = module.deploy_provider_setup.deploy_default_tags }
  dynamic "assume_role" {
    for_each = module.deploy_provider_setup.deploy_settings.role_arn == null ? [] : [0]
    content {
      session_name = module.deploy_provider_setup.session_name
      role_arn     = module.deploy_provider_setup.deploy_settings.role_arn
    }
  }
}

provider "aws" {
  alias   = "main"
  region  = module.deploy_provider_setup.deploy_settings.region
  profile = module.deploy_provider_setup.deploy_settings.deploy_profile
  default_tags { tags = merge(module.deploy_provider_setup.deploy_default_tags, { TerraformProvider = "main" }) }
  dynamic "assume_role" {
    for_each = module.deploy_provider_setup.deploy_settings.role_arn == null ? [] : [0]
    content {
      session_name = module.deploy_provider_setup.session_name
      role_arn     = module.deploy_provider_setup.deploy_settings.role_arn
    }
  }
}

provider "aws" {
  alias   = "global"
  region  = module.deploy_provider_setup.deploy_settings.region
  profile = module.deploy_provider_setup.deploy_settings.deploy_profile
  default_tags { tags = merge(module.deploy_provider_setup.deploy_default_tags, { TerraformProvider = "global" }) }
  dynamic "assume_role" {
    for_each = module.deploy_provider_setup.deploy_settings.role_arn == null ? [] : [0]
    content {
      session_name = module.deploy_provider_setup.session_name
      role_arn     = module.deploy_provider_setup.deploy_settings.role_arn
    }
  }
}
