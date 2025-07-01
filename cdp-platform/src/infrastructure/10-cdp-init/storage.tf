locals {
  cdp_file_path = tolist(fileset("../..", "build/dist/cdp_tools-*"))[0]
}

module "cdp_tools_lib" {
  source                     = "../../../../terraform-modules/storage/storage_file"
  bucket_name                = module.code_bucket.name
  key_arn                    = module.regional_settings.value.secrets_key_arn
  local_path_relative_to_src = local.cdp_file_path
  remote_file_path           = "cdp_platform/${basename(local.cdp_file_path)}"
  tags                       = local.tags
}

module "code_bucket" {
  source      = "../../../../terraform-modules/storage/simple_bucket_delete_forbidden"
  name        = "${local.bucket_prefix}-code-storage"
  description = "Code storage for custom data processing"
  tags        = local.tags
  key_arn     = module.regional_settings.value.secrets_key_arn
  logging     = { bucket = module.regional_settings.value.s3_logging_bucket_name }
}
