locals {
  name_prefix = "${var.project_name}-${var.environment}"

  # Pull exactly 2 AZs in the selected region.
  azs = slice(data.aws_availability_zones.available.names, 0, 2)

  # /20 subnets under a /16 VPC (10.0.0.0/16 → 10.0.0.0/20, 10.0.16.0/20, ...).
  public_subnet_cidrs  = [cidrsubnet(var.vpc_cidr, 4, 0), cidrsubnet(var.vpc_cidr, 4, 1)]
  private_subnet_cidrs = [cidrsubnet(var.vpc_cidr, 4, 2), cidrsubnet(var.vpc_cidr, 4, 3)]

  # Secret names we mint — the application reads these via ECS task definition.
  app_secret_names = [
    "DATABASE_URL",
    "JWT_SECRET",
    "TOTP_ENCRYPTION_KEY",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_PRICE_ID",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "DEEPGRAM_API_KEY",
    "RESEND_API_KEY",
    "SENTRY_DSN",
  ]
}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}
