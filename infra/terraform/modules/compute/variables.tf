variable "project_name" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

# Networking
variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for Fargate tasks"
  type        = list(string)
}

variable "alb_security_group_id" {
  description = "ALB security group ID"
  type        = string
}

variable "ecs_security_group_id" {
  description = "ECS tasks security group ID"
  type        = string
}

# Database
variable "db_endpoint" {
  description = "Database endpoint"
  type        = string
}

variable "db_port" {
  description = "Database port"
  type        = number
}

variable "db_name" {
  description = "Database name"
  type        = string
}

variable "db_username" {
  description = "Database username"
  type        = string
}

variable "db_secret_arn" {
  description = "ARN of the DB master password secret"
  type        = string
}

# Cache
variable "redis_endpoint" {
  description = "Redis endpoint"
  type        = string
}

variable "redis_port" {
  description = "Redis port"
  type        = number
}

# Storage
variable "s3_bucket_name" {
  description = "S3 bucket name"
  type        = string
}

variable "s3_bucket_arn" {
  description = "S3 bucket ARN"
  type        = string
}

# Compute sizing
variable "api_cpu" {
  description = "CPU units for API task"
  type        = number
}

variable "api_memory" {
  description = "Memory for API task in MB"
  type        = number
}

variable "worker_cpu" {
  description = "CPU units for worker tasks"
  type        = number
}

variable "worker_memory" {
  description = "Memory for worker tasks in MB"
  type        = number
}

variable "api_desired_count" {
  description = "Number of API task instances"
  type        = number
}

variable "worker_desired_count" {
  description = "Number of worker task instances"
  type        = number
}

variable "container_image" {
  description = "Container image override"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Common tags"
  type        = map(string)
  default     = {}
}
