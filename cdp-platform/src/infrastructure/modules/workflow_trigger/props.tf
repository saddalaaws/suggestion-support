variable "prefix" {
  type        = string
  description = "Prefix of the lambda / execution ids and subscriptions"
}

variable "path" {
  type        = string
  description = "Path for the lambda function role"
}

variable "security_group_map" {
  type        = map(string)
  description = "Map with the available security groups"
}

variable "upload_window_seconds" {
  type        = number
  description = "Number of seconds for the upload window"
  default     = 10 * 60
}

variable "tags" {
  type        = map(string)
  description = "List of tags for the resources"
}

variable "upload_notification_topic_arn" {
  type        = string
  description = "ARN of SNS topic to which the input bucket write their S3 upload notifications"
}

variable "upload_triggers" {
  type = list(object({
    check_only    = bool
    file_selector = string
    workflow_settings = object({
      name       = string
      arn        = string
      parameters = string
    })
  }))
  description = "Upload trigger settings"
  default     = []
}

variable "scheduled_triggers" {
  type = list(object({
    schedule_expression = string
    workflow_settings = object({
      name       = string
      arn        = string
      parameters = string
    })
  }))
  description = "Schedule trigger settings"
  default     = []
}
