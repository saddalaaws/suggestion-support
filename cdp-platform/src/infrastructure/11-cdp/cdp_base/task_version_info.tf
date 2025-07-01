module "version_lambda" {
  for_each        = toset(var.scope == "br" ? ["3.10", "3.11"] : [])
  source          = "../../../../../terraform-modules/services/lambda_function_with_role"
  name            = "${local.prefix}-version-info-${replace(each.key, ".", "-")}"
  description     = "Lambda function to get version infos"
  source_path     = "lambda_functions/version_info"
  runtime         = "python${each.key}"
  lambda_settings = merge(local.lambda_settings, { common_layers = [] })
  path            = local.path
  tags            = local.tags
  security_groups = [
    var.cdp_settings_from_ics.security_group_map.allow_access_from_private_subnet,
    var.cdp_settings_from_ics.security_group_map.allow_access_to_private_subnet,
    var.cdp_settings_from_ics.security_group_map.allow_access_to_s3,
    var.cdp_settings_from_ics.security_group_map.allow_access_to_dynamodb,
    var.cdp_settings_from_ics.security_group_map.allow_access_to_internet,
  ]
  # Permissions are only needed for functional test of endpoints and inconsequential at first order
  role_permissions = {
    statements = [
      {
        sid       = "AllowCodeReadAccess"
        actions   = ["s3:GetBucketWebsite"]
        resources = [module.storage_bucket.arn]
      },
      {
        sid       = "AllowLambdaRunDBAccess"
        actions   = ["dynamodb:DescribeLimits"]
        resources = ["*"]
      },
      {
        sid       = "AllowToInspectLayers"
        actions   = ["lambda:ListLayerVersions"]
        resources = ["*"]
      }
    ]
    environment = {
      "test_bucket" : module.storage_bucket.name,
      "test_layers" : jsonencode(var.cdp_settings_from_ics.lambda_settings.common_layers),
    }
  }
}

module "version_glue" {
  for_each      = toset(var.scope == "br" ? ["glue-4.0", "glue-5.0", "shell-3.9", "shell-3.9:ana"] : [])
  source        = "../../../../../terraform-modules/services/glue_job_with_role"
  source_path   = "lambda_functions/version_info/version_info.py"
  glue_settings = local.glue_settings
  temp_path     = "${module.workspace.output_path}/glue"
  name_base     = replace(replace("version_${each.value}", ".", ""), ":", "")
  glue_version  = split(":", each.value)[0]
  connections   = var.cdp_settings_from_ics.glue_connection_map.with_internet
  default_arguments = merge({
    "--mode"             = each.value
    "--JOB_NAME"         = "test-${replace(replace("version_${each.value}", ".", ""), ":", "")}",
    "--disable-proxy-v2" = "true",
    "--test_bucket"      = module.storage_bucket.name,
    "--test_layers"      = jsonencode(var.cdp_settings_from_ics.lambda_settings.common_layers),
    },
    each.value == "shell-3.9:ana" ? {
      "library-set" : "analytics"
    } : {},
  )
  requirements = []
  role_permissions = {
    statements = [
      local.glue_source_code_access_statement,
      module.code_bucket_key_access.statement,
      {
        sid       = "AllowCodeReadAccess"
        actions   = ["s3:GetBucketWebsite"]
        resources = [module.storage_bucket.arn]
      },
      {
        sid       = "AllowLambdaRunDBAccess"
        actions   = ["dynamodb:DescribeLimits"]
        resources = ["*"]
      },
      {
        sid       = "AllowToInspectLayers"
        actions   = ["lambda:ListLayerVersions"]
        resources = ["*"]
      },
      {
        sid       = "AllowToWriteAnyLogs"
        actions   = ["logs:*"]
        resources = ["*"]
      }
    ]
  }
}
