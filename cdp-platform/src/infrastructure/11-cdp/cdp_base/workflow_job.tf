data "aws_cloudwatch_log_group" "task_log_group" {
  name = var.cdp_account_settings.task_log_group_name
}

module "custom_processing_glue_job" {
  source              = "../../../../../terraform-modules/services/glue_job_with_role"
  source_path         = "glue_jobs/custom_data_processing.py"
  glue_settings       = local.glue_settings
  max_concurrent_runs = var.task_concurrency
  temp_path           = "${module.workspace.output_path}/glue"
  glue_version        = "glue-5.0"
  connections         = var.cdp_settings_from_ics.glue_connection_map.with_internet
  default_arguments = {
    "--config_lambda_arn" = module.configure_jobs.arn
    "--scope"             = var.scope
    "--task_log_group"    = var.cdp_account_settings.task_log_group_name
    "--user_task_config"  = "null"
  }
  role_permissions = {
    statements = [
      local.glue_source_code_access_statement,
      module.code_bucket_key_access.statement,
      {
        sid = "AllowGlueToRunConfigLambda"
        resources = [
          module.configure_jobs.arn,
          # TODO(platform): Access the global Lambda ARN directly
          # 7099
          "arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:global-*",
        ]
        actions = ["lambda:InvokeFunction"]
      },
      {
        sid       = "AllowGlueToWriteTaskLogs"
        resources = ["${data.aws_cloudwatch_log_group.task_log_group.arn}:*"]
        actions = [
          "logs:CreateLogStream", # arn:aws:logs:${local.region_name}:${local.account_id}:log-group:${LogGroupName}:log-stream:${LogStreamName} (resource_tags); * ()
          "logs:PutLogEvents",    # arn:aws:logs:${local.region_name}:${local.account_id}:log-group:${LogGroupName}:log-stream:${LogStreamName} (resource_tags); * ()
        ]
      },
      {
        sid       = "AllowGlueToUseStorageKeys"
        resources = ["*"]
        actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
      },
      {
        sid       = "AllowGlueToReadWriteStorage"
        resources = ["*"]
        actions = [
          "s3:AbortMultipartUpload",
          "s3:DeleteObject",
          "s3:GetBucketLocation",
          "s3:GetObject",
          "s3:GetObjectAcl",
          "s3:GetObjectVersion",
          "s3:ListBucket",
          "s3:ListMultipartUploadParts",
          "s3:PutObject",
          "s3:PutObjectAcl",
        ]
      },
      {
        sid       = "AllowGlueToReadWriteGlueTables"
        resources = ["*"]
        actions = [
          "glue:CreateDatabase", # arn:aws:glue:${local.region_name}:${local.account_id}:catalog (); arn:aws:glue:${local.region_name}:${local.account_id}:database/${DatabaseName} (); * ()
          "glue:CreateTable",    # arn:aws:glue:${local.region_name}:${local.account_id}:catalog (); arn:aws:glue:${local.region_name}:${local.account_id}:database/${DatabaseName} (); * ()
          "glue:GetDatabase",    # arn:aws:glue:${local.region_name}:${local.account_id}:catalog (); arn:aws:glue:${local.region_name}:${local.account_id}:database/${DatabaseName} (); * ()
          "glue:GetDatabases",   # arn:aws:glue:${local.region_name}:${local.account_id}:catalog (); arn:aws:glue:${local.region_name}:${local.account_id}:database/${DatabaseName} (); * ()
          "glue:DeleteTable",    # arn:aws:glue:${local.region_name}:${local.account_id}:catalog (); arn:aws:glue:${local.region_name}:${local.account_id}:database/${DatabaseName} (); arn:aws:glue:${local.region_name}:${local.account_id}:table/${DatabaseName}/${TableName} (); * ()
          "glue:GetPartitions",  # arn:aws:glue:${local.region_name}:${local.account_id}:catalog (); arn:aws:glue:${local.region_name}:${local.account_id}:database/${DatabaseName} (); arn:aws:glue:${local.region_name}:${local.account_id}:table/${DatabaseName}/${TableName} (); * ()
          "glue:GetTable",       # arn:aws:glue:${local.region_name}:${local.account_id}:catalog (); arn:aws:glue:${local.region_name}:${local.account_id}:database/${DatabaseName} (); arn:aws:glue:${local.region_name}:${local.account_id}:table/${DatabaseName}/${TableName} (); * ()
          "glue:GetTables",      # arn:aws:glue:${local.region_name}:${local.account_id}:catalog (); arn:aws:glue:${local.region_name}:${local.account_id}:database/${DatabaseName} (); arn:aws:glue:${local.region_name}:${local.account_id}:table/${DatabaseName}/${TableName} (); * ()
          "glue:UpdateTable",    # arn:aws:glue:${local.region_name}:${local.account_id}:catalog (); arn:aws:glue:${local.region_name}:${local.account_id}:database/${DatabaseName} (); arn:aws:glue:${local.region_name}:${local.account_id}:table/${DatabaseName}/${TableName} (); * ()
        ]
      },
      {
        sid       = "AllowAthenaAccess"
        resources = ["*"]
        actions = [
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
          "athena:StartQueryExecution",
          "athena:GetWorkGroup",
        ]
      },
      {
        sid       = "AllowTranslateAccess"
        resources = ["*"]
        actions = [
          "translate:TranslateText",
        ]
      },
      {
        sid       = "AllowComprehendAccess"
        resources = ["*"]
        actions = [
          "comprehend:StartDocumentClassificationJob",
          "comprehend:DetectDominantLanguage",
        ]
      },
      {
        sid       = "AllowGlueToWriteSecrets"
        resources = ["*"]
        actions = [
          "secretsmanager:GetSecretValue", # arn:aws:secretsmanager:${local.region_name}:${local.account_id}:secret:${SecretId} (request_tags|resource_tags|aws:TagKeys|secretsmanager:ResourceTag/tag-key|secretsmanager:SecretId|secretsmanager:SecretPrimaryRegion|secretsmanager:VersionId|secretsmanager:VersionStage|secretsmanager:resource/AllowRotationLambdaArn); * (resource_tags|secretsmanager:ResourceTag/tag-key|secretsmanager:SecretId|secretsmanager:SecretPrimaryRegion|secretsmanager:VersionId|secretsmanager:VersionStage|secretsmanager:resource/AllowRotationLambdaArn)
          "secretsmanager:PutSecretValue", # arn:aws:secretsmanager:${local.region_name}:${local.account_id}:secret:${SecretId} (request_tags|resource_tags|aws:TagKeys|secretsmanager:ResourceTag/tag-key|secretsmanager:SecretId|secretsmanager:SecretPrimaryRegion|secretsmanager:resource/AllowRotationLambdaArn); * (resource_tags|secretsmanager:ResourceTag/tag-key|secretsmanager:SecretId|secretsmanager:SecretPrimaryRegion|secretsmanager:resource/AllowRotationLambdaArn)
        ]
      },
      {
        sid       = "AllowUploadAcrossAccounts"
        resources = [local.sanitization_target_arn]
        actions   = ["sts:AssumeRole"]
      },
    ]
  }
}
