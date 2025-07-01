locals {
  sanitization_enabled             = false # contains(var.task_list, "sanitization") # FIXME enable after rollout
  sanitization_target_account_name = "dev"
  sanitization_source_account_name = "staging"
  sanitization_target_account_id   = var.account_name_to_account_id_map[local.sanitization_target_account_name]
  sanitization_source_account_id   = var.account_name_to_account_id_map[local.sanitization_source_account_name]
  sanitization_target_prefix       = "${var.base_settings.project}-${local.sanitization_target_account_name}-${var.scope}"
  sanitization_source_prefix       = "${var.base_settings.project}-${local.sanitization_source_account_name}-${var.scope}"
  sanitization_target_role_suffix  = "sanitization-upload-role"
  sanitization_source_role_suffix  = trimprefix(reverse(split("/", module.custom_processing_glue_job.role_arn))[0], "${local.sanitization_target_prefix}-")
  sanitization_target_arn          = "arn:aws:iam::${local.sanitization_target_account_id}:role/${var.base_settings.project}/${local.sanitization_target_account_name}/${var.scope}/${local.sanitization_target_prefix}-${local.sanitization_target_role_suffix}"
  sanitization_source_arn          = "arn:aws:iam::${local.sanitization_source_account_id}:role/${var.base_settings.project}/${local.sanitization_source_account_name}/${var.scope}/${local.sanitization_source_prefix}-${local.sanitization_source_role_suffix}"
}

module "sanitization_upload_role" {
  count              = local.sanitization_enabled && (var.base_settings.account_name == local.sanitization_target_account_name) ? 1 : 0
  source             = "../../../../../terraform-modules/security/role"
  name               = "${local.prefix}-${local.sanitization_target_role_suffix}"
  path               = local.path
  assumable_by_users = [local.sanitization_source_arn]
  boundary_arn       = var.base_settings.boundary_arn
  description        = "This role is used by the sanitization script to upload files"
  tags               = local.tags
  statements = [
    {
      sid       = "AllowWriteAccessToStorageBucket1"
      resources = ["*"]
      actions = [
        "s3:AbortMultipartUpload",
        "s3:DeleteObject",
        "s3:GetObject",
        "s3:GetObjectAcl",
        "s3:ListMultipartUploadParts",
        "s3:PutObject",
        "s3:PutObjectAcl",
      ]
    },
    {
      sid       = "AllowWriteAccessToStorageBucket2"
      resources = ["*"]
      actions   = ["s3:ListBucketMultipartUploads", "s3:ListBucket"]
    },
    {
      # Multipart uploads need to be decrypted when they are reassembled
      sid       = module.storage_key.read_write_access_statement.sid
      actions   = module.storage_key.read_write_access_statement.actions
      resources = ["*"]
    },
  ]
}
