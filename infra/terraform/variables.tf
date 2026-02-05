variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "therapy-rag"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

# Networking
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

# Database
variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage in GB"
  type        = number
  default     = 20
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "therapy_rag"
}

variable "db_username" {
  description = "PostgreSQL master username"
  type        = string
  default     = "therapy_admin"
}

# Cache
variable "cache_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.t3.micro"
}

# Compute
variable "api_cpu" {
  description = "CPU units for API task (1024 = 1 vCPU)"
  type        = number
  default     = 256
}

variable "api_memory" {
  description = "Memory for API task in MB"
  type        = number
  default     = 512
}

variable "worker_cpu" {
  description = "CPU units for worker tasks"
  type        = number
  default     = 256
}

variable "worker_memory" {
  description = "Memory for worker tasks in MB"
  type        = number
  default     = 512
}

variable "api_desired_count" {
  description = "Number of API task instances"
  type        = number
  default     = 1
}

variable "worker_desired_count" {
  description = "Number of worker task instances (per worker type)"
  type        = number
  default     = 1
}

variable "container_image" {
  description = "Docker image for the application"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}
