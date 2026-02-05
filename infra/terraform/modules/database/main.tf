################################################################################
# RDS PostgreSQL with pgvector
################################################################################

resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-${var.environment}"
  subnet_ids = var.subnet_ids

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-db-subnet-group"
  })
}

resource "aws_db_parameter_group" "postgres" {
  name_prefix = "${var.project_name}-${var.environment}-"
  family      = "postgres16"
  description = "PostgreSQL 16 with pgvector support"

  # pgvector requires shared_preload_libraries
  parameter {
    name         = "shared_preload_libraries"
    value        = "pg_stat_statements"
    apply_method = "pending-reboot"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }

  tags = var.tags

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_db_instance" "main" {
  identifier = "${var.project_name}-${var.environment}"

  engine         = "postgres"
  engine_version = "16.4"
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.allocated_storage * 2
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  # Password managed via AWS Secrets Manager or SSM Parameter Store
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.security_group_id]
  parameter_group_name   = aws_db_parameter_group.postgres.name

  multi_az            = false
  publicly_accessible = false

  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"

  skip_final_snapshot       = var.environment != "prod"
  final_snapshot_identifier = var.environment == "prod" ? "${var.project_name}-final" : null
  deletion_protection       = var.environment == "prod"

  performance_insights_enabled = false

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-postgres"
  })
}

# SSM Parameter for database endpoint (free, unlike Secrets Manager)
resource "aws_ssm_parameter" "db_host" {
  name  = "/${var.project_name}/${var.environment}/database/host"
  type  = "String"
  value = aws_db_instance.main.address

  tags = var.tags
}

resource "aws_ssm_parameter" "db_port" {
  name  = "/${var.project_name}/${var.environment}/database/port"
  type  = "String"
  value = tostring(aws_db_instance.main.port)

  tags = var.tags
}

resource "aws_ssm_parameter" "db_name" {
  name  = "/${var.project_name}/${var.environment}/database/name"
  type  = "String"
  value = var.db_name

  tags = var.tags
}
