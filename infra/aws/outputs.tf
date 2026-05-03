output "alb_dns_name" {
  description = "Public DNS of the application load balancer."
  value       = aws_lb.this.dns_name
}

output "rds_endpoint" {
  description = "RDS Postgres endpoint (host:port)."
  value       = aws_db_instance.this.endpoint
  sensitive   = true
}

output "redis_endpoint" {
  description = "ElastiCache Redis primary endpoint."
  value       = aws_elasticache_replication_group.this.primary_endpoint_address
  sensitive   = true
}

output "s3_bucket_name" {
  description = "Recordings S3 bucket name."
  value       = aws_s3_bucket.recordings.bucket
}

output "s3_bucket_arn" {
  description = "Recordings S3 bucket ARN."
  value       = aws_s3_bucket.recordings.arn
}

output "ecs_cluster_arn" {
  description = "ECS cluster ARN."
  value       = aws_ecs_cluster.this.arn
}

output "app_service_name" {
  description = "Name of the app ECS service."
  value       = aws_ecs_service.app.name
}

output "worker_service_name" {
  description = "Name of the worker ECS service."
  value       = aws_ecs_service.worker.name
}

output "secrets_arns" {
  description = "ARNs of all app-level Secrets Manager entries."
  value       = [for s in aws_secretsmanager_secret.app : s.arn]
}

output "vpc_id" {
  description = "VPC ID."
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "Private subnet IDs."
  value       = module.vpc.private_subnets
}

output "public_subnet_ids" {
  description = "Public subnet IDs."
  value       = module.vpc.public_subnets
}

output "recordings_kms_key_arn" {
  description = "KMS key ARN protecting recordings."
  value       = aws_kms_key.recordings.arn
}

output "alerts_sns_topic_arn" {
  description = "SNS topic receiving CloudWatch alarms."
  value       = aws_sns_topic.alerts.arn
}
