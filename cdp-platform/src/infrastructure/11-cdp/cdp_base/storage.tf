module "storage_key" {
  source      = "../../../../../terraform-modules/security/kms_key_delete_forbidden"
  name        = "${local.prefix}-key"
  description = "KMS key for the output bucket"
  path        = local.path
  tags        = local.tags
}

module "storage_backup_key" {
  source      = "../../../../../terraform-modules/security/kms_key_delete_forbidden"
  name        = "${local.prefix}-backup-key"
  description = "KMS key for the output bucket"
  path        = local.path
  tags        = local.tags
  providers = {
    aws = aws.backup
  }
}

module "storage_bucket" {
  source      = "../../../../../terraform-modules/storage/simple_bucket_delete_forbidden"
  name        = "${local.bucket_prefix}-storage"
  description = "Storage for custom data processing ${var.scope}"
  tags        = local.tags
  key_arn     = module.storage_key.arn
  logging     = { bucket = var.cdp_settings_from_ics.s3_logging_bucket_name }
}

module "storage_backup_bucket" {
  count       = 0 # Disabled
  source      = "../../../../../terraform-modules/storage/simple_bucket_delete_forbidden"
  name        = "${local.bucket_prefix}-storage-dr"
  description = "Storage for custom data processing ${var.scope}"
  tags        = local.tags
  key_arn     = module.storage_backup_key.arn
  logging     = { bucket = var.cdp_settings_from_ics.s3_logging_bucket_name }
}

module "run_info_setup" {
  source           = "../../../../../terraform-modules/storage/storage_file"
  bucket_name      = var.cdp_code_settings.code_bucket_name
  key_arn          = var.cdp_code_settings.code_bucket_key_arn
  remote_file_path = "run_info/${var.scope}.json"
  content = jsonencode({
    lambda_arn = module.configure_jobs.arn
  })
  tags = local.tags
}
