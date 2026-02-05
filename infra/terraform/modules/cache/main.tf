################################################################################
# ElastiCache Redis
################################################################################

resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project_name}-${var.environment}"
  subnet_ids = var.subnet_ids

  tags = var.tags
}

resource "aws_elasticache_cluster" "main" {
  cluster_id           = "${var.project_name}-${var.environment}"
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = var.node_type
  num_cache_nodes      = 1
  port                 = 6379
  parameter_group_name = "default.redis7"

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [var.security_group_id]

  snapshot_retention_limit = 0
  maintenance_window       = "Mon:05:00-Mon:06:00"

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-redis"
  })
}

# SSM Parameter for Redis endpoint
resource "aws_ssm_parameter" "redis_host" {
  name  = "/${var.project_name}/${var.environment}/cache/host"
  type  = "String"
  value = aws_elasticache_cluster.main.cache_nodes[0].address

  tags = var.tags
}

resource "aws_ssm_parameter" "redis_port" {
  name  = "/${var.project_name}/${var.environment}/cache/port"
  type  = "String"
  value = tostring(aws_elasticache_cluster.main.cache_nodes[0].port)

  tags = var.tags
}
