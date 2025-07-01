variable "name" {
  type        = string
  description = "Name of the workflow"
}

variable "state_name" {
  type        = string
  description = "Name of the first workflow state"
}

variable "description" {
  type        = string
  description = "Description of the workflow"
}

variable "main_branch" {
  type        = string
  description = "JSON encoded main branch"
}

variable "enable_user_discovery" {
  type        = bool
  description = "JSON encoded main branch"
  default     = false
}

variable "teams_secret_name" {
  type        = string
  description = "Name of the teams secret"
  default     = ""
}

variable "teams_channel" {
  type        = string
  description = "Name of the channel in the secret"
  default     = ""
}

variable "error_parser_info" {
  type = object({
    arn         = string,
    name        = string,
    environment = map(string),
    payload     = map(map(any))
  })
  description = "Infos of the error parser function"
}

variable "notification_topic_arn" {
  type        = string
  description = "ARN of the SNS notification topic"
}

output "name" {
  value       = var.name
  description = "Name of the workflow"
}

output "json" {
  value       = jsonencode(local.workflow_definition)
  description = "JSON definition of the workflow"
}
