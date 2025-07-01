locals {
  glue_settings = merge(
    var.cdp_settings_from_ics.glue_settings,
    {
      boundary_arn       = var.base_settings.boundary_arn
      source_bucket_name = var.cdp_code_settings.code_bucket_name
      source_key_arn     = var.cdp_code_settings.code_bucket_key_arn
      path               = local.path
      prefix             = local.prefix
      tags               = local.tags
    }
  )

  glue_source_code_access_statement = {
    sid       = "AllowCDPCodeAccess"
    resources = [var.cdp_code_settings.code_bucket_files_arn]
    actions   = ["s3:GetObject"]
  }

  lambda_settings = merge(
    var.cdp_settings_from_ics.lambda_settings,
    { boundary_arn = var.base_settings.boundary_arn },
  )
}

module "code_bucket_key_access" {
  source  = "../../../../../terraform-modules/security/kms_key_statement"
  key_arn = var.cdp_code_settings.code_bucket_key_arn
  actions = ["kms:GenerateDataKey", "kms:Decrypt"]
}

module "error_parser" {
  source          = "../../../../../terraform-modules/services/lambda_function_with_role"
  name            = "${local.prefix}-workflow-error-parser"
  description     = "Lambda function to process error messages of the workflow"
  tags            = local.tags
  source_path     = "lambda_functions/error_parser"
  lambda_settings = local.lambda_settings
  runtime         = "python3.10"
  path            = local.path
  timeout         = 120
  security_groups = [
    var.cdp_settings_from_ics.security_group_map.allow_access_from_private_subnet,
    var.cdp_settings_from_ics.security_group_map.allow_access_to_private_subnet,
    var.cdp_settings_from_ics.security_group_map.allow_access_to_internet,
  ]
  role_permissions = {
    statements = concat(
      [
        {
          sid       = "AllowLambdaToAccessStepFunction"
          actions   = ["states:GetExecutionHistory"]
          resources = ["arn:aws:states:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:execution:${local.workflow_sfn_name}"]
        },
        {
          sid       = "AllowLambdaToAccessTeamsSecret1"
          actions   = ["secretsmanager:GetSecretValue"]
          resources = [data.aws_secretsmanager_secret.teams_secret.arn]
        },
        {
          sid       = "AllowLambdaToAccessTeamsSecret2"
          actions   = ["kms:Decrypt"]
          resources = [var.cdp_settings_from_ics.secrets_key_arn, data.aws_kms_key.secrets_key.arn]
        },
      ]
    )
  }
}

locals {
  # The default policy for the workflow is to not retry failed steps,
  # but retry if the number of concurrent runs is reached
  workflow_retry_policy = [{
    "ErrorEquals" : ["Glue.ConcurrentRunsExceededException"],
    "IntervalSeconds" : 60,
    "MaxAttempts" : 10,
    "BackoffRate" : 1.1
  }]

  workflow_main = {
    "StartAt" : "Configure Jobs",

    "States" : {
      "Configure Jobs" : {
        "Type" : "Task",
        "Resource" : "arn:aws:states:::lambda:invoke",
        "Parameters" : {
          "FunctionName" : module.configure_jobs.arn,
          "Payload" : {
            "mode"          = "get-sfn-jobs"
            "user_config.$" = "$",
            "job_name_map" = {
              "python" : module.custom_processing_glue_job.name,
            }
          }
        },
        "ResultPath" : "$",
        "OutputPath" : "$.Payload"
        "Retry" : local.workflow_retry_policy,
        "Next" : "Custom Data Processing"
      }

      "Custom Data Processing" : {
        "Type" : "Map",
        "ItemsPath" : "$.job_list",
        "MaxConcurrency" : var.task_concurrency,
        "ResultPath" : "$",
        "Retry" : local.workflow_retry_policy,
        "End" : true,

        "Iterator" : {
          "StartAt" : "Running Task",
          "States" : {
            "Running Task" : {
              "Type" : "Task",
              "Resource" : "arn:aws:states:::glue:startJobRun.sync",
              "Parameters" : {
                "JobName.$" : "$.job_name"
                "Arguments" : {
                  "--additional-python-modules.$" : "$.additional_python_modules",
                  "--task_name.$" : "$.task_name",
                  "--user_task_config.$" : "States.JsonToString($.user_task_config)",
                }
              },
              "ResultPath" : "$.job_output",
              "Retry" : local.workflow_retry_policy,
              "Catch" : [{
                "ErrorEquals" : ["States.ALL"],
                "ResultPath" : "$.error",
                "Next" : "Task Completed",
              }],
              "Next" : "Task Completed",
            },
            "Task Completed" : {
              "Type" : "Pass",
              "End" : true
            }
          }
        }
      }
    }
  }
}

locals {
  # This is used to break the circular dependency for the lambda permissions
  workflow_sfn_name = "${local.prefix}-task-workflow"
  teams_secret_name = "ics-${var.base_settings.account_name}-global-teams-hook"
}

data "aws_kms_key" "secrets_key" {
  key_id = var.cdp_settings_from_ics.secrets_key_arn
}

data "aws_secretsmanager_secret" "teams_secret" {
  name = local.teams_secret_name
}

module "workflow_wrapper" {
  source                 = "../../modules/sfn_error_handler"
  name                   = local.workflow_sfn_name
  state_name             = "CDP Tasks"
  description            = "CDP Tasks state machine"
  main_branch            = jsonencode(local.workflow_main)
  error_parser_info      = module.error_parser.info
  notification_topic_arn = var.cdp_settings_from_ics.user_notifications_topic_setup.topic_arn
  enable_user_discovery  = false
  teams_secret_name      = local.teams_secret_name
  teams_channel          = "cdp"
}

module "workflow" {
  source          = "../../../../../terraform-modules/services/step_function"
  name            = module.workflow_wrapper.name
  tags            = local.tags
  definition_json = module.workflow_wrapper.json
  role_arn        = module.workflow_log_and_role.role_arn
  log_arn         = module.workflow_log_and_role.log_arn
}

module "workflow_log_and_role" {
  source          = "../../../../../terraform-modules/services/step_function_log_and_role"
  name            = "${local.prefix}-workflow-role"
  description     = "Execution role for the ${local.prefix} workflow step function"
  tags            = local.tags
  boundary_arn    = var.base_settings.boundary_arn
  path            = var.cdp_settings_from_ics.path
  logging_key_arn = var.cdp_settings_from_ics.logging_key_arn
  services_permissions = {
    lambda = [
      module.configure_jobs.arn,
      module.error_parser.arn,
    ]
    glue = [
      module.custom_processing_glue_job.arn
    ]
    sns = [
      var.cdp_settings_from_ics.user_notifications_topic_setup
    ]
  }
}

module "workflow_trigger" {
  source                        = "../../modules/workflow_trigger"
  upload_notification_topic_arn = var.cdp_settings_from_ics.input_upload_notification_topic_arn
  prefix                        = local.prefix
  path                          = local.path
  lambda_settings               = local.lambda_settings
  tags                          = local.tags
  security_group_map            = var.cdp_settings_from_ics.security_group_map

  upload_triggers = []
  scheduled_triggers = [
    {
      schedule_expression = "rate(1 hour)"
      workflow_settings = {
        name       = "auto_{timestamp}_{uuid}"
        arn        = module.workflow.arn
        parameters = jsonencode({ "check_schedule" : true })
      }
    }
  ]
}
