variable "task_list" {
  description = "List of CDP tasks"
  type        = list(string)
}

variable "account_name_to_account_id_map" {
  description = "Map from account name to account id"
  type        = map(string)
}

variable "cdp_account_settings" {
  description = "CDP Account Settings"
  type = object({
    task_log_group_name = string
  })
}

variable "cdp_code_settings" {
  description = "CDP Code Settings"
  type = object({
    code_bucket_arn            = string
    code_bucket_name           = string
    code_bucket_files_arn      = string
    code_bucket_key_arn        = string
    code_bucket_s3_path_prefix = string
    cdp_tools_lib_path         = string
  })
}

variable "cdp_settings_from_ics" {
  description = "CDP Platform settings"
  type = object({
    backup_region = string
    country       = string
    glue_connection_map = map(list(object({
      name = string
      arn  = string
    })))
    glue_settings = object({
      boundary_arn               = string
      logging_key_arn            = string
      path                       = string
      glue_default_policy_arn    = string
      glue_connection_policy_arn = string
      prefix                     = string
      security_configuration     = string
      source_bucket_name         = string
      source_key_arn             = string
      tags                       = map(string)
    })
    input_bucket_name_map               = map(string)
    input_upload_notification_topic_arn = string
    lambda_settings = object({
      boundary_arn  = string
      common_layers = list(string)
      dead_letter_topic_setup = object({
        topic_arn = string
        topic_producer_statements = list(object({
          sid       = string
          actions   = list(string)
          resources = list(string)
        }))
      })
      lambda_test_db = object({
        table_arn = string
        hash_key  = string
      })
      lambda_key_arn    = string
      trusted_sso_roles = list(string)
      vpc_subnets       = list(string)
    })
    logging_key_arn             = string
    path                        = string
    preprocessing_database_name = string
    region                      = string
    run_db_arn                  = string
    run_db_key_access_statement = object({
      sid       = string
      actions   = list(string)
      resources = list(string)
    })
    run_db_name            = string
    s3_logging_bucket_name = string
    secrets_key_arn        = string
    security_group_map     = map(string)
    sfn_bu_list            = list(string)
    user_notifications_topic_setup = object({
      topic_arn = string
      topic_producer_statements = list(object({
        sid       = string
        actions   = list(string)
        resources = list(string)
      }))
    })
  })
}

variable "scope" {
  description = "Short name of the project scope"
  type        = string
}

variable "grafana_role_arn" {
  description = "ARN of the Grafana role"
  type        = string
}

variable "task_concurrency" {
  description = "Number of concurrent CDP tasks"
  type        = number
  default     = 10
}

locals {
  path          = "/${var.base_settings.project}/${var.base_settings.account_name}/${var.scope}"
  prefix        = "${var.base_settings.project}-${var.base_settings.account_name}-${var.scope}"
  bucket_prefix = "merck-${local.prefix}"
  tags = {
    Env     = local.prefix
    Country = var.scope
    Stage   = var.base_settings.account_name
  }
}

data "aws_region" "current" {}

data "aws_caller_identity" "current" {}
