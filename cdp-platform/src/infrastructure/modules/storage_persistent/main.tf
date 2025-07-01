terraform {
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      configuration_aliases = [aws.backup]
      version               = "~> 5.90"
    }
  }
  required_version = "= 1.11.1"
}

resource "aws_s3_bucket" "bucket" {
  bucket = var.name

  lifecycle {
    prevent_destroy = false
  }

  tags = merge(var.tags, {
    Name = var.description
  })
}

resource "aws_s3_bucket_public_access_block" "bucket_access_block" {
  bucket                  = aws_s3_bucket.bucket.bucket
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "bucket" {
  bucket = aws_s3_bucket.bucket.id
  policy = data.aws_iam_policy_document.policy.json
}

resource "aws_s3_bucket_server_side_encryption_configuration" "bucket" {
  bucket = aws_s3_bucket.bucket.id
  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = var.key_arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_website_configuration" "bucket" {
  bucket = aws_s3_bucket.bucket.id
  redirect_all_requests_to {
    host_name = "localhost"
  }
}

resource "aws_s3_bucket_logging" "bucket" {
  bucket        = aws_s3_bucket.bucket.id
  target_bucket = var.log_bucket
  target_prefix = "${var.log_prefix}/"
}

resource "aws_s3_bucket_versioning" "bucket" {
  bucket = aws_s3_bucket.bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "bucket" {
  count  = var.backup_replication ? 0 : 1
  bucket = aws_s3_bucket.bucket.id
  rule {
    status = "Enabled"
    id     = "Delete unused old version files after 8 weeks "
    noncurrent_version_expiration {
      noncurrent_days = 56
    }
  }
}

resource "aws_s3_bucket_replication_configuration" "bucket" {
  count  = var.backup_replication ? 1 : 0
  bucket = aws_s3_bucket.bucket.id
  role   = aws_iam_role.replication_role[0].arn

  rule {
    id     = "Damage recovery replication rule"
    status = "Enabled"

    destination {
      bucket        = aws_s3_bucket.bucket_backup[0].arn
      storage_class = "INTELLIGENT_TIERING"
      encryption_configuration {
        replica_kms_key_id = var.backup_key_arn
      }
    }

    source_selection_criteria {
      sse_kms_encrypted_objects {
        status = "Enabled"
      }
    }
  }

  depends_on = [aws_s3_bucket_versioning.bucket]
}

data "aws_iam_policy_document" "policy" {
  statement {
    sid     = "BucketSSLPolicy"
    effect  = "Deny"
    actions = ["*"]
    resources = [
    "arn:aws:s3:::${var.name}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

locals {
  replication_bucket_name = "${var.name}-dr"
}

resource "aws_s3_bucket" "bucket_backup" {
  count    = var.backup_replication ? 1 : 0
  provider = aws.backup
  bucket   = local.replication_bucket_name

  lifecycle {
    prevent_destroy = false
  }

  tags = merge(var.tags, {
    Name = "Replication target for ${var.description}"
  })
}

resource "aws_s3_bucket_public_access_block" "bucket_access_block_backup" {
  count                   = var.backup_replication ? 1 : 0
  provider                = aws.backup
  bucket                  = aws_s3_bucket.bucket_backup[0].bucket
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "bucket_backup" {
  count    = var.backup_replication ? 1 : 0
  provider = aws.backup
  bucket   = aws_s3_bucket.bucket_backup[0].id
  policy   = data.aws_iam_policy_document.bucket_backup_policy[0].json
}

resource "aws_s3_bucket_server_side_encryption_configuration" "bucket_backup" {
  count    = var.backup_replication ? 1 : 0
  provider = aws.backup
  bucket   = aws_s3_bucket.bucket_backup[0].id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = var.backup_key_arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_versioning" "bucket_backup" {
  count    = var.backup_replication ? 1 : 0
  provider = aws.backup
  bucket   = aws_s3_bucket.bucket_backup[0].id
  versioning_configuration {
    status = "Enabled"
  }
}

data "aws_kms_key" "key" {
  key_id = var.key_arn
}

data "aws_kms_key" "backup_key" {
  count    = var.backup_replication ? 1 : 0
  provider = aws.backup
  key_id   = var.backup_key_arn
}

resource "aws_iam_role" "replication_role" {
  count                = var.backup_replication ? 1 : 0
  name                 = "${var.prefix}-replication-role"
  path                 = "${var.path}/"
  assume_role_policy   = data.aws_iam_policy_document.assume_role_policy[0].json
  permissions_boundary = var.boundary_arn
  tags                 = var.tags
}

data "aws_iam_policy_document" "assume_role_policy" {
  count = var.backup_replication ? 1 : 0
  statement {
    sid     = "AllowAssumeRole"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "replication_policy" {
  count  = var.backup_replication ? 1 : 0
  name   = "${var.prefix}-replication-policy"
  role   = aws_iam_role.replication_role[0].name
  policy = data.aws_iam_policy_document.replication_policy[0].json
}

data "aws_iam_policy_document" "replication_policy" {
  count = var.backup_replication ? 1 : 0
  statement {
    actions = [
      "s3:ListBucket",
      "s3:GetReplicationConfiguration",
      "s3:GetObjectVersionForReplication",
      "s3:GetObjectVersionAcl",
      "s3:GetObjectVersionTagging",
      "s3:GetObjectRetention",
      "s3:GetObjectLegalHold"
    ]
    resources = [
      aws_s3_bucket.bucket.arn,
      "${aws_s3_bucket.bucket.arn}/*"
    ]
  }

  statement {
    actions = [
      "s3:ReplicateObject",
      "s3:ReplicateDelete",
      "s3:ReplicateTags",
      "s3:GetObjectVersionTagging"
    ]
    condition {
      test     = "StringLikeIfExists"
      variable = "s3:x-amz-server-side-encryption"
      values = [
        "aws:kms",
        "AES256"
      ]
    }
    condition {
      test     = "StringLikeIfExists"
      variable = "s3:x-amz-server-side-encryption-aws-kms-key-id"
      values   = [data.aws_kms_key.backup_key[0].arn]
    }
    resources = ["${aws_s3_bucket.bucket_backup[0].arn}/*"]
  }

  statement {
    actions = [
      "kms:Decrypt"
    ]
    condition {
      test     = "StringLike"
      variable = "kms:ViaService"
      values = [
        "s3.${aws_s3_bucket.bucket.region}.amazonaws.com"
      ]
    }
    condition {
      test     = "StringLike"
      variable = "kms:EncryptionContext:aws:s3:arn"
      values = [
        "${aws_s3_bucket.bucket.arn}/*"
      ]
    }
    resources = [data.aws_kms_key.key.arn]
  }

  statement {
    actions = [
      "kms:Encrypt"
    ]
    condition {
      test     = "StringLike"
      variable = "kms:ViaService"
      values = [
        "s3.${aws_s3_bucket.bucket_backup[0].region}.amazonaws.com"
      ]
    }
    condition {
      test     = "StringLike"
      variable = "kms:EncryptionContext:aws:s3:arn"
      values = [
        "${aws_s3_bucket.bucket_backup[0].arn}/*"
      ]
    }
    resources = [data.aws_kms_key.backup_key[0].arn]
  }
}

data "aws_iam_policy_document" "bucket_backup_policy" {
  count = var.backup_replication ? 1 : 0
  statement {
    sid       = "BucketSSLPolicy"
    effect    = "Deny"
    actions   = ["*"]
    resources = ["arn:aws:s3:::${local.replication_bucket_name}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}
