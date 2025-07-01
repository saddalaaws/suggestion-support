resource "aws_cloudwatch_log_group" "task_log" {
  name              = "${local.path}/task-log"
  tags              = local.tags
  kms_key_id        = module.regional_settings.value.logging_key_arn
  retention_in_days = 3653
  lifecycle {
    prevent_destroy = true
  }
}
