################################################################################
# S3 Bucket (replaces MinIO)
################################################################################

resource "aws_s3_bucket" "recordings" {
  bucket = "${var.project_name}-${var.environment}-recordings"

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-recordings"
  })
}

resource "aws_s3_bucket_versioning" "recordings" {
  bucket = aws_s3_bucket.recordings.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "recordings" {
  bucket = aws_s3_bucket.recordings.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "recordings" {
  bucket = aws_s3_bucket.recordings.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "recordings" {
  bucket = aws_s3_bucket.recordings.id

  rule {
    id     = "transition-to-ia"
    status = "Enabled"

    filter {}

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
  }
}

# SSM Parameter for bucket name
resource "aws_ssm_parameter" "bucket_name" {
  name  = "/${var.project_name}/${var.environment}/storage/bucket"
  type  = "String"
  value = aws_s3_bucket.recordings.id

  tags = var.tags
}
