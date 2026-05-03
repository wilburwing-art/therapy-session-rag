variable "project_name" {
  description = "Short project identifier used as a name prefix for all resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment (e.g. dev, staging, prod)."
  type        = string
}

variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "domain_name" {
  description = "Fully-qualified domain for the public endpoint (ACM cert + Route53 A record)."
  type        = string
}

variable "hosted_zone_id" {
  description = "Route53 hosted zone ID that owns domain_name."
  type        = string
}

variable "app_image" {
  description = "ECR image URI (with tag or digest) for the backend app."
  type        = string
}

variable "worker_image" {
  description = "ECR image URI for the RQ worker. May equal app_image."
  type        = string
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t3.medium"
}

variable "db_allocated_storage" {
  description = "Allocated storage for RDS in GB."
  type        = number
  default     = 100
}

variable "db_max_allocated_storage" {
  description = "Upper bound for RDS storage autoscaling in GB."
  type        = number
  default     = 500
}

variable "db_name" {
  description = "Initial database name."
  type        = string
  default     = "therapyrag"
}

variable "db_username" {
  description = "Master username for RDS."
  type        = string
  default     = "therapyrag"
}

variable "redis_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t3.micro"
}

variable "desired_count" {
  description = "Desired Fargate task count for the app service."
  type        = number
  default     = 2
}

variable "app_cpu" {
  description = "Fargate CPU units for the app task."
  type        = number
  default     = 512
}

variable "app_memory" {
  description = "Fargate memory (MiB) for the app task."
  type        = number
  default     = 1024
}

variable "worker_cpu" {
  description = "Fargate CPU units for the worker task."
  type        = number
  default     = 256
}

variable "worker_memory" {
  description = "Fargate memory (MiB) for the worker task."
  type        = number
  default     = 512
}

variable "worker_desired_count" {
  description = "Desired Fargate task count for the worker service."
  type        = number
  default     = 1
}

variable "alert_email" {
  description = "Email address subscribed to the CloudWatch SNS alert topic."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days."
  type        = number
  default     = 90
}

variable "tags" {
  description = "Additional tags merged into provider default_tags."
  type        = map(string)
  default     = {}
}
