module "workspace" {
  source                = "../../../../../terraform-modules/data_management/data_environment_single"
  name                  = local.prefix
  description           = "Workspace for CDP ${local.prefix}"
  tags                  = local.tags
  short_name            = "cdp"
  output_bucket_s3_path = "${module.storage_bucket.s3_path}/cdp_platform/workspace"
  output_key_arn        = module.storage_key.arn
}
