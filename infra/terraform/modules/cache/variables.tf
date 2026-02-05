variable "project_name" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "node_type" {
  description = "ElastiCache node type"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for cache subnet group"
  type        = list(string)
}

variable "security_group_id" {
  description = "Security group ID for cache access"
  type        = string
}

variable "tags" {
  description = "Common tags"
  type        = map(string)
  default     = {}
}
