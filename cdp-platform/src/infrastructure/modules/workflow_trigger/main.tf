locals {
  schedule_expression_list = [
    for entry in var.scheduled_triggers :
    entry.schedule_expression
  ]
  schedule_expression_dict = {
    for schedule_expression in local.schedule_expression_list :
    substr(md5(schedule_expression), 0, 4) => schedule_expression
  }
  workflow_arn_list = distinct(concat(
    [for entry in var.upload_triggers : entry.workflow_settings.arn],
    [for entry in var.scheduled_triggers : entry.workflow_settings.arn],
  ))
  upload_triggers_enabled = length(var.upload_triggers) == 0
}


module "configured_schedule_expressions" {
  for_each            = local.schedule_expression_dict
  source              = "../../../../../terraform-modules/services/lambda_trigger"
  name                = "${var.prefix}-workflow-schedule-${each.key}"
  description         = "Triggers Lambda function to trigger workflows"
  tags                = var.tags
  schedule_expression = each.value
  arguments           = { "schedule_expression" : each.value }
  target              = module.lambda_function.arn
}

module "upload_database_drain_schedule" {
  count               = local.upload_triggers_enabled ? 0 : 1
  source              = "../../../../../terraform-modules/services/lambda_trigger"
  name                = "${var.prefix}-workflow-schedule-drain"
  description         = "Triggers Lambda function to drain the upload database"
  tags                = var.tags
  schedule_expression = "rate(5 minutes)"
  arguments           = { "drain" : true }
  target              = module.lambda_function.arn
}

resource "aws_lambda_permission" "upload_sns_topic_sub" {
  count         = local.upload_triggers_enabled ? 0 : 1
  statement_id  = "AllowExecutionFromSNStopic"
  principal     = "sns.amazonaws.com"
  action        = "lambda:InvokeFunction"
  source_arn    = var.upload_notification_topic_arn
  function_name = module.lambda_function.arn
}

resource "aws_sns_topic_subscription" "upload_notification" {
  count     = local.upload_triggers_enabled ? 0 : 1
  topic_arn = var.upload_notification_topic_arn
  protocol  = "lambda"
  endpoint  = module.lambda_function.arn
}

module "upload_db" {
  count       = local.upload_triggers_enabled ? 0 : 1
  source      = "../../../../../terraform-modules/services/dynamodb_table"
  name        = "${var.prefix}-workflow-upload-trigger-db"
  description = "Trigger Upload Database"
  tags        = var.tags
  key_arn     = var.lambda_settings.lambda_key_arn
  hash_key = {
    name = "upload_path"
    type = "S"
  }
}

module "lambda_function" {
  source          = "../../../../../terraform-modules/services/lambda_function_with_role"
  name            = "${var.prefix}-workflow-trigger"
  description     = "Lambda function that manages automatic workflow execution."
  tags            = var.tags
  path            = var.path
  source_path     = "lambda_functions/workflow_trigger"
  lambda_settings = var.lambda_settings
  runtime         = "python3.10"
  security_groups = [
    var.security_group_map.allow_access_from_private_subnet,
    var.security_group_map.allow_access_to_private_subnet,
    var.security_group_map.allow_access_to_dynamodb,
  ]
  environment = {
    "UPLOAD_WINDOW_SECONDS" = var.upload_window_seconds,
    "UPLOAD_TABLE_NAME"     = local.upload_triggers_enabled ? "" : module.upload_db[0].name,
    "UPLOAD_TRIGGERS"       = jsonencode(var.upload_triggers),
    "SCHEDULED_TRIGGERS"    = jsonencode(var.scheduled_triggers),
  }
  role_permissions = {
    statements = concat([
      {
        sid       = "AllowStartTarget"
        actions   = ["states:StartExecution"]
        resources = local.workflow_arn_list
      }
      ],
      local.upload_triggers_enabled ? [] : [
        {
          sid = "AllowLambdaUploadDBAccess"
          actions = [
            "dynamodb:BatchWriteItem",
            "dynamodb:DeleteItem",
            "dynamodb:GetItem",
            "dynamodb:PutItem",
            "dynamodb:Scan",
          ]
          resources = [module.upload_db[0].arn]
        }
      ]
    )
  }
}
