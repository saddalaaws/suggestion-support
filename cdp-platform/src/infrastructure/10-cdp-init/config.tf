locals {
  path          = "/${local.project}/${local.account_name}"
  prefix        = "${local.project}-${local.account_name}"
  bucket_prefix = "merck-${local.prefix}"
  account_name  = terraform.workspace
  project       = local.deploy_settings.project

  tags = {
    Env   = local.prefix
    Stage = local.account_name
  }

  # Terraform provider deploy settings
  deploy_settings = module.deploy_provider_setup.deploy_settings

  # Tasks that require dedicated secrets
  task_secret_to_default_secret_map = merge(
    {
      "channel_segmentation" : {
        "basetable-secret" : "",
      }

      "dynamic_call_plan" : {
        "token" : "",
      }

      "dynamic_call_plan_email" : {
        "app_id" : "",
        "app_secret" : "",
        "tenant_id" : "",
      }
    },
    local.account_name == "prod" ? {} : {
      "automated_email_tagging" : {
        "client_id_de" : "",
        "secret_id_de" : "",
        "client_id_body" : "",
        "secret_id_body" : "",
      },
    }
  )
}

data "aws_region" "current" {}

module "regional_settings" {
  source = "../../../../terraform-modules/config_storage/parameter_reader"
  name   = "/ics/${local.account_name}/region_settings/${data.aws_region.current.name}"
}

module "cdp_settings_from_ics" {
  source    = "../../../../terraform-modules/config_storage/recursive_parameter_reader"
  name      = "/${local.project}/${local.account_name}/platform_settings/"
  providers = { aws = aws.global }
}

module "cdp_settings" {
  source      = "../../../../terraform-modules/config_storage/parameter_writer"
  name        = "/${local.project}/${local.account_name}/account_settings"
  description = "Secret that contains the code storage settings for the custom data processing"
  tags        = local.tags
  key_arn     = module.regional_settings.value.secrets_key_arn
  value = {
    task_log_group_name = aws_cloudwatch_log_group.task_log.name
  }
  providers = { aws = aws.global }
}

module "code_settings" {
  source      = "../../../../terraform-modules/config_storage/parameter_writer"
  name        = "/${local.project}/${local.account_name}/code_settings"
  description = "Secret that contains the code storage settings for the custom data processing"
  tags        = local.tags
  key_arn     = module.regional_settings.value.secrets_key_arn
  value = {
    code_bucket_arn            = module.code_bucket.arn
    code_bucket_name           = module.code_bucket.name
    code_bucket_files_arn      = module.code_bucket.files_arn,
    code_bucket_key_arn        = module.regional_settings.value.secrets_key_arn
    code_bucket_s3_path_prefix = "${module.code_bucket.s3_path}/tasks"
    cdp_tools_lib_path         = module.cdp_tools_lib.s3_path
  }
  providers = { aws = aws.global }
}

output "scope_list" {
  description = "List of scopes to deploy"
  value = [
    for entry in values(module.cdp_settings_from_ics.value) : entry.country
    if split("-", entry.country)[0] != "test"
  ]
}
