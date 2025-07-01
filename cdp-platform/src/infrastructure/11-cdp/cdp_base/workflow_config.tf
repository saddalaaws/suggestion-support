locals {
  input_database_name_map = merge(
    {
      shared = var.cdp_settings_from_ics.preprocessing_database_name
    },
    {
      for bu_name in var.cdp_settings_from_ics.sfn_bu_list :
      bu_name => var.cdp_settings_from_ics.preprocessing_database_name
      if bu_name != "core"
    }
  )
}

module "configure_jobs" {
  source          = "../../../../../terraform-modules/services/lambda_function_with_role"
  name            = "${local.prefix}-configure-jobs"
  description     = "Lambda function that configures the CDP tasks"
  tags            = local.tags
  source_path     = "lambda_functions/configure_jobs"
  lambda_settings = local.lambda_settings
  memory          = 1024
  runtime         = "python3.10"
  path            = local.path
  security_groups = [
    var.cdp_settings_from_ics.security_group_map.allow_access_from_private_subnet,
    var.cdp_settings_from_ics.security_group_map.allow_access_to_dynamodb,
    var.cdp_settings_from_ics.security_group_map.allow_access_to_private_subnet,
    var.cdp_settings_from_ics.security_group_map.allow_access_to_s3,
  ]
  extra_files = {
    "cdp_tools/__init__.py" : "cdp_tools/__init__.py",
  }
  environment = {
    ACCOUNT_NAME                = var.base_settings.account_name
    ALLOWED_TASKS               = jsonencode(var.task_list)
    CDP_TOOLS_WHEEL             = var.cdp_code_settings.cdp_tools_lib_path
    CONFIG_FILE_DIR             = var.cdp_code_settings.code_bucket_s3_path_prefix
    PREPROCESSING_DATABASE_NAME = var.cdp_settings_from_ics.preprocessing_database_name
    RUN_DB_KEY                  = local.prefix
    RUN_DB_TABLE                = var.cdp_settings_from_ics.run_db_name
    SCOPE                       = var.scope

    TASK_ENV = jsonencode({
      CDP_ENV_ACCOUNT_NAME          = jsonencode(var.base_settings.account_name)
      CDP_ENV_DATABASE_NAME         = jsonencode(module.workspace.database_name)
      CDP_ENV_INPUT_BUCKET_NAME_MAP = jsonencode(var.cdp_settings_from_ics.input_bucket_name_map)
      CDP_ENV_INPUT_DATABASE_MAP    = jsonencode(local.input_database_name_map)
      CDP_ENV_PREFIX                = jsonencode(local.prefix)
      CDP_ENV_SCOPE                 = jsonencode(var.scope)
      CDP_ENV_STORAGE_BUCKET_NAME   = jsonencode(module.storage_bucket.name)
      CDP_ENV_STORAGE_KEY_ARN       = jsonencode(module.storage_key.arn)
      CDP_ENV_SFN_BU_LIST           = jsonencode(var.cdp_settings_from_ics.sfn_bu_list)
      CDP_ENV_STORAGE_PATH          = jsonencode(module.storage_bucket.s3_path)
      CDP_ENV_WORKSPACE_NAME        = jsonencode(module.workspace.workgroup_name)
    })
  }
  role_permissions = {
    statements = concat(
      [
        {
          sid       = "AllowCodeReadAccess"
          actions   = ["s3:GetObject"]
          resources = [var.cdp_code_settings.code_bucket_files_arn]
        },
        module.code_bucket_key_access.statement,
        {
          sid       = "AllowLambdaRunDBAccess"
          actions   = ["dynamodb:GetItem", "dynamodb:PutItem"]
          resources = [var.cdp_settings_from_ics.run_db_arn]
        },
        var.cdp_settings_from_ics.run_db_key_access_statement,
      ],
    )
  }
}
