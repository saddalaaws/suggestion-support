variable "lambda_settings" {
  description = "Common settings for Lambda functions"
  type = object({
    boundary_arn      = string
    common_layers     = list(string)
    lambda_key_arn    = string
    trusted_sso_roles = optional(list(string), [])
    vpc_subnets       = list(string)
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
  })
}
