variable "base_settings" {
  description = "Base settings that are set in the same way for every country"
  type = object({
    project      = string
    account_name = string
    boundary_arn = string
  })
}
