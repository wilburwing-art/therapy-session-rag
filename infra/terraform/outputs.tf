################################################################################
# Networking
################################################################################

output "vpc_id" {
  description = "VPC ID"
  value       = module.networking.vpc_id
}

################################################################################
# Database
################################################################################

output "db_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = module.database.db_endpoint
}

output "db_port" {
  description = "RDS PostgreSQL port"
  value       = module.database.db_port
}

################################################################################
# Cache
################################################################################

output "redis_endpoint" {
  description = "ElastiCache Redis endpoint"
  value       = module.cache.redis_endpoint
}

################################################################################
# Storage
################################################################################

output "s3_bucket_name" {
  description = "S3 recordings bucket name"
  value       = module.storage.bucket_name
}

################################################################################
# Compute
################################################################################

output "ecr_repository_url" {
  description = "ECR repository URL for Docker images"
  value       = module.compute.ecr_repository_url
}

output "alb_dns_name" {
  description = "Application Load Balancer DNS name"
  value       = module.compute.alb_dns_name
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = module.compute.cluster_name
}

################################################################################
# Convenience: connection strings
################################################################################

output "api_url" {
  description = "API base URL"
  value       = "http://${module.compute.alb_dns_name}"
}
