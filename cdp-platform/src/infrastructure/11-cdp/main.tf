locals {
  account_name = split("-", terraform.workspace)[0]
  scope        = split("-", terraform.workspace)[1]
  # Terraform provider deploy settings
  deploy_settings = module.deploy_provider_setup.deploy_settings
  project         = local.deploy_settings.project

  scope_list = concat(["global"], [for entry in module.cdp_settings_from_ics.value : entry.country])

  cdp_settings_from_ics = one([for entry in module.cdp_settings_from_ics.value : entry if entry.country == local.scope])
  # Tmp solution would be updated after ics repo update
  is_active_scope = local.cdp_settings_from_ics != null
  active_tasks    = lookup(lookup(local.account_scope_tasks_map, local.account_name, {}), local.scope, [])
}

module "cdp_settings_from_ics" {
  source    = "../../../../terraform-modules/config_storage/recursive_parameter_reader"
  name      = "/${local.project}/${local.account_name}/platform_settings/"
  providers = { aws = aws.global }
}

module "cdp_account_settings" {
  source    = "../../../../terraform-modules/config_storage/parameter_reader"
  name      = "/${local.project}/${local.account_name}/account_settings"
  providers = { aws = aws.global }
}

module "cdp_code_settings" {
  source    = "../../../../terraform-modules/config_storage/parameter_reader"
  name      = "/${local.project}/${local.account_name}/code_settings"
  providers = { aws = aws.global }
}

module "platform" {
  count                          = local.is_active_scope ? 1 : 0
  source                         = "./cdp_base"
  scope                          = local.scope
  task_list                      = local.active_tasks
  cdp_settings_from_ics          = local.cdp_settings_from_ics
  cdp_account_settings           = module.cdp_account_settings.value
  cdp_code_settings              = module.cdp_code_settings.value
  account_name_to_account_id_map = local.deploy_settings.parameters.account_name_to_account_id_map
  grafana_role_arn               = module.grafana_settings.value.grafana_role_arn
  base_settings = {
    account_name = local.account_name
    project      = local.project
    boundary_arn = local.deploy_settings.parameters.boundary_arn
  }

  providers = {
    aws        = aws
    aws.global = aws.main
    aws.main   = aws.main
    aws.backup = aws.backup
    grafana    = grafana
  }
}
