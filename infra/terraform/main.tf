################################################################################
# Provider
################################################################################

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

################################################################################
# Locals
################################################################################

locals {
  common_tags = merge(var.tags, {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

################################################################################
# Networking
################################################################################

module "networking" {
  source = "./modules/networking"

  project_name       = var.project_name
  environment        = var.environment
  aws_region         = var.aws_region
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  tags               = local.common_tags
}

################################################################################
# Database
################################################################################

module "database" {
  source = "./modules/database"

  project_name      = var.project_name
  environment       = var.environment
  instance_class    = var.db_instance_class
  allocated_storage = var.db_allocated_storage
  db_name           = var.db_name
  db_username       = var.db_username
  subnet_ids        = module.networking.private_subnet_ids
  security_group_id = module.networking.database_security_group_id
  tags              = local.common_tags
}

################################################################################
# Cache
################################################################################

module "cache" {
  source = "./modules/cache"

  project_name      = var.project_name
  environment       = var.environment
  node_type         = var.cache_node_type
  subnet_ids        = module.networking.private_subnet_ids
  security_group_id = module.networking.cache_security_group_id
  tags              = local.common_tags
}

################################################################################
# Storage
################################################################################

module "storage" {
  source = "./modules/storage"

  project_name = var.project_name
  environment  = var.environment
  tags         = local.common_tags
}

################################################################################
# Compute
################################################################################

module "compute" {
  source = "./modules/compute"

  project_name          = var.project_name
  environment           = var.environment
  aws_region            = var.aws_region
  vpc_id                = module.networking.vpc_id
  public_subnet_ids     = module.networking.public_subnet_ids
  alb_security_group_id = module.networking.alb_security_group_id
  ecs_security_group_id = module.networking.ecs_security_group_id

  db_endpoint  = module.database.db_endpoint
  db_port      = module.database.db_port
  db_name      = var.db_name
  db_username  = var.db_username
  db_secret_arn = module.database.db_master_user_secret_arn

  redis_endpoint = module.cache.redis_endpoint
  redis_port     = module.cache.redis_port

  s3_bucket_name = module.storage.bucket_name
  s3_bucket_arn  = module.storage.bucket_arn

  api_cpu              = var.api_cpu
  api_memory           = var.api_memory
  worker_cpu           = var.worker_cpu
  worker_memory        = var.worker_memory
  api_desired_count    = var.api_desired_count
  worker_desired_count = var.worker_desired_count
  container_image      = var.container_image

  tags = local.common_tags
}
