module "task_secrets" {
  for_each          = local.task_secret_to_default_secret_map
  source            = "../../../../terraform-modules/config_storage/secret_placeholder_delete_forbidden"
  name              = "${local.project}-${local.account_name}-${each.key}"
  description       = "Changes are picked up immediately: Secret for ${each.key}"
  tags              = local.tags
  key_arn           = module.regional_settings.value.secrets_key_arn
  rotation_settings = module.regional_settings.value.rotation_settings
  default_secret    = each.value
}
