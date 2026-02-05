################################################################################
# ECR Repository
################################################################################

resource "aws_ecr_repository" "app" {
  name                 = "${var.project_name}-${var.environment}"
  image_tag_mutability = "MUTABLE"
  force_delete         = var.environment != "prod"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-ecr"
  })
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 5 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 5
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

################################################################################
# ECS Cluster
################################################################################

resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "disabled"
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-cluster"
  })
}

################################################################################
# CloudWatch Log Groups
################################################################################

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.project_name}-${var.environment}/api"
  retention_in_days = 14

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "worker_transcription" {
  name              = "/ecs/${var.project_name}-${var.environment}/worker-transcription"
  retention_in_days = 14

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "worker_embedding" {
  name              = "/ecs/${var.project_name}-${var.environment}/worker-embedding"
  retention_in_days = 14

  tags = var.tags
}

################################################################################
# IAM: ECS Task Execution Role
################################################################################

data "aws_iam_policy_document" "ecs_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_execution" {
  name               = "${var.project_name}-${var.environment}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow reading SSM parameters for config
data "aws_iam_policy_document" "ssm_read" {
  statement {
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath",
    ]
    resources = ["arn:aws:ssm:${var.aws_region}:*:parameter/${var.project_name}/${var.environment}/*"]
  }

  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.db_secret_arn]
  }
}

resource "aws_iam_policy" "ssm_read" {
  name   = "${var.project_name}-${var.environment}-ssm-read"
  policy = data.aws_iam_policy_document.ssm_read.json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "ssm_read" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = aws_iam_policy.ssm_read.arn
}

################################################################################
# IAM: ECS Task Role (runtime permissions)
################################################################################

resource "aws_iam_role" "ecs_task" {
  name               = "${var.project_name}-${var.environment}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json

  tags = var.tags
}

data "aws_iam_policy_document" "task_permissions" {
  statement {
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [
      var.s3_bucket_arn,
      "${var.s3_bucket_arn}/*",
    ]
  }

  statement {
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
    ]
    resources = ["arn:aws:ssm:${var.aws_region}:*:parameter/${var.project_name}/${var.environment}/*"]
  }
}

resource "aws_iam_policy" "task_permissions" {
  name   = "${var.project_name}-${var.environment}-task-permissions"
  policy = data.aws_iam_policy_document.task_permissions.json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "task_permissions" {
  role       = aws_iam_role.ecs_task.name
  policy_arn = aws_iam_policy.task_permissions.arn
}

################################################################################
# ALB
################################################################################

resource "aws_lb" "main" {
  name               = "${var.project_name}-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-alb"
  })
}

resource "aws_lb_target_group" "api" {
  name        = "${var.project_name}-${var.environment}-api"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }

  tags = var.tags
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  tags = var.tags
}

################################################################################
# Task Definitions
################################################################################

locals {
  container_image = var.container_image != "" ? var.container_image : "${aws_ecr_repository.app.repository_url}:latest"

  common_environment = [
    { name = "ENVIRONMENT", value = var.environment },
    { name = "POSTGRES_HOST", value = var.db_endpoint },
    { name = "POSTGRES_PORT", value = tostring(var.db_port) },
    { name = "POSTGRES_DB", value = var.db_name },
    { name = "POSTGRES_USER", value = var.db_username },
    { name = "REDIS_HOST", value = var.redis_endpoint },
    { name = "REDIS_PORT", value = tostring(var.redis_port) },
    { name = "MINIO_ENDPOINT", value = "s3.${var.aws_region}.amazonaws.com" },
    { name = "MINIO_BUCKET", value = var.s3_bucket_name },
    { name = "MINIO_USE_SSL", value = "true" },
    { name = "AWS_REGION", value = var.aws_region },
  ]
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project_name}-${var.environment}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = local.container_image
      essential = true

      command = ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]

      environment = local.common_environment

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }
    }
  ])

  tags = var.tags
}

resource "aws_ecs_task_definition" "worker_transcription" {
  family                   = "${var.project_name}-${var.environment}-worker-transcription"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "worker-transcription"
      image     = local.container_image
      essential = true

      command = ["python", "-m", "rq.cli", "worker", "transcription", "--url", "redis://${var.redis_endpoint}:${var.redis_port}"]

      environment = local.common_environment

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.worker_transcription.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])

  tags = var.tags
}

resource "aws_ecs_task_definition" "worker_embedding" {
  family                   = "${var.project_name}-${var.environment}-worker-embedding"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "worker-embedding"
      image     = local.container_image
      essential = true

      command = ["python", "-m", "rq.cli", "worker", "embedding", "--url", "redis://${var.redis_endpoint}:${var.redis_port}"]

      environment = local.common_environment

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.worker_embedding.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])

  tags = var.tags
}

################################################################################
# ECS Services
################################################################################

resource "aws_ecs_service" "api" {
  name            = "api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [var.ecs_security_group_id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.http]

  tags = var.tags
}

resource "aws_ecs_service" "worker_transcription" {
  name            = "worker-transcription"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker_transcription.arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [var.ecs_security_group_id]
    assign_public_ip = true
  }

  tags = var.tags
}

resource "aws_ecs_service" "worker_embedding" {
  name            = "worker-embedding"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker_embedding.arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [var.ecs_security_group_id]
    assign_public_ip = true
  }

  tags = var.tags
}
