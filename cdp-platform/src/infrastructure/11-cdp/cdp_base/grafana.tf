module "grafana_athena_datasource" {
  source                = "../../../../../terraform-modules/grafana/athena_datasource"
  name                  = "athena-cdp-${var.scope}"
  description           = "Athena CDP workspace"
  tags                  = local.tags
  path                  = local.path
  boundary_arn          = var.base_settings.boundary_arn
  prefix                = "${var.base_settings.project}-${var.base_settings.account_name}" # Scope is added via name
  grafana_role_arn      = var.grafana_role_arn
  source_bucket_arn     = module.storage_bucket.arn
  source_key_arn        = module.storage_key.arn
  tmp_data_env_settings = module.workspace
  tmp_key_arn           = module.storage_key.arn
}

module "monitoring_settings" {
  source      = "../../../../../terraform-modules/config_storage/parameter_writer"
  name        = "/${var.base_settings.project}/${var.base_settings.account_name}/monitoring_settings/${var.scope}"
  description = "Secret that contains settings for monitoring purposes"
  tags        = local.tags
  key_arn     = var.cdp_settings_from_ics.secrets_key_arn
  value = {
    country      = var.cdp_settings_from_ics.country
    region       = var.cdp_settings_from_ics.region
    workflow_arn = module.workflow.arn
  }
  providers = { aws = aws.global }
}
