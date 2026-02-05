# Dev environment configuration
# Optimized for free tier + minimal Fargate costs

project_name = "therapy-rag"
environment  = "dev"
aws_region   = "us-east-1"

# Networking
vpc_cidr           = "10.0.0.0/16"
availability_zones = ["us-east-1a", "us-east-1b"]

# Database: Free tier eligible
db_instance_class    = "db.t3.micro"
db_allocated_storage = 20
db_name              = "therapy_rag"
db_username          = "therapy_admin"

# Cache: Free tier eligible
cache_node_type = "cache.t3.micro"

# Compute: Minimal sizing
# Scale desired_count to 0 when not demoing to save ~$10/month
api_cpu              = 256
api_memory           = 512
worker_cpu           = 256
worker_memory        = 512
api_desired_count    = 1
worker_desired_count = 1

tags = {
  CostCenter = "personal"
  Purpose    = "portfolio-demo"
}
