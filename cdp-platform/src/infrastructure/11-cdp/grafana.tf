module "grafana_settings" {
  source    = "../../../../terraform-modules/config_storage/parameter_reader"
  name      = "/ics/${local.account_name}/grafana"
  providers = { aws = aws.global }
}

provider "grafana" {
  url  = module.grafana_settings.value.provider_url
  auth = module.grafana_settings.value.provider_key
}
