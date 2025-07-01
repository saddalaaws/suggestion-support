variable "name" {
  type        = string
  description = "Name of the storage bucket"
}

variable "description" {
  type        = string
  description = "Description of the storage bucket"
}

variable "prefix" {
  type        = string
  description = "Prefix for the encryption key and replication role"
}

variable "boundary_arn" {
  type        = string
  description = "Name of the permission boundary for the replication role"
}

variable "log_bucket" {
  type        = string
  description = "Name of the logging bucket"
}

variable "log_prefix" {
  type        = string
  description = "Prefix for the folder on the logging bucket"
}

variable "tags" {
  type        = map(string)
  description = "List of tags for the resources"
}

variable "path" {
  type        = string
  description = "Path for the KMS keys and replication roles"
}

variable "key_arn" {
  type        = string
  description = "ARN of the storage KMS key"
}

variable "backup_key_arn" {
  type        = string
  description = "ARN of the storage backup KMS key"
  default     = ""
}

variable "backup_replication" {
  description = "Enable disaster recovery via cross-regional replication to another bucket"
  type        = bool
}

output "name" {
  value       = aws_s3_bucket.bucket.bucket
  description = "Name of the storage bucket"
}

output "arn" {
  value       = aws_s3_bucket.bucket.arn
  description = "ARN of the storage bucket"
}

output "files_arn" {
  value       = "${aws_s3_bucket.bucket.arn}/*"
  description = "ARN of files in the storage bucket"
}

output "key_access_statement" {
  value = {
    sid       = "AllowKeyAccess${replace(title(var.prefix), "-", "")}"
    actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
    resources = [var.key_arn, data.aws_kms_key.key.arn]
  }
  description = "ARN of the storage bucket key and alias (the alias is there for intrinsic documentation)"
}

output "s3_path" {
  value       = "s3://${var.name}"
  description = "S3 path to the storage bucket"
}
