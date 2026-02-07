# Deployment Guide

This guide covers deploying TherapyRAG to AWS using Terraform.

## Prerequisites

- AWS CLI configured with appropriate credentials
- Terraform >= 1.5.0
- Docker for building container images
- API keys for external services:
  - Deepgram (transcription)
  - OpenAI (embeddings)
  - Anthropic/Claude (chat)

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         AWS Cloud                                │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                      VPC (10.0.0.0/16)                      ││
│  │  ┌──────────────────────┐  ┌──────────────────────┐        ││
│  │  │   Public Subnets     │  │   Private Subnets    │        ││
│  │  │  ┌────────────────┐  │  │  ┌────────────────┐  │        ││
│  │  │  │      ALB       │  │  │  │  RDS Postgres  │  │        ││
│  │  │  │  (port 443)    │──┼──│  │  (pgvector)    │  │        ││
│  │  │  └────────────────┘  │  │  └────────────────┘  │        ││
│  │  │           │          │  │                      │        ││
│  │  │  ┌────────────────┐  │  │  ┌────────────────┐  │        ││
│  │  │  │  ECS Fargate   │  │  │  │  ElastiCache   │  │        ││
│  │  │  │  - API         │──┼──│  │  (Redis)       │  │        ││
│  │  │  │  - Workers     │  │  │  └────────────────┘  │        ││
│  │  │  └────────────────┘  │  │                      │        ││
│  │  └──────────────────────┘  └──────────────────────┘        ││
│  └─────────────────────────────────────────────────────────────┘│
│                              │                                  │
│                    ┌─────────┴─────────┐                       │
│                    │    S3 Bucket      │                       │
│                    │  (recordings)     │                       │
│                    └───────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
```

## Components

| Component | AWS Service | Purpose |
|-----------|-------------|---------|
| Database | RDS PostgreSQL | Primary data store with pgvector |
| Cache | ElastiCache Redis | Job queue, rate limiting, caching |
| Storage | S3 | Audio recording storage |
| Compute | ECS Fargate | API server and background workers |
| Load Balancer | ALB | HTTPS termination, routing |
| Networking | VPC | Network isolation |

## Quick Start

### 1. Clone and Configure

```bash
cd infra/terraform

# Copy example variables
cp terraform.tfvars.example terraform.tfvars

# Edit with your values
vim terraform.tfvars
```

### 2. Set Required Variables

Edit `terraform.tfvars`:

```hcl
project_name = "therapy-rag"
environment  = "dev"
aws_region   = "us-east-1"

# Database
db_instance_class    = "db.t3.micro"    # Use db.t3.small+ for production
db_allocated_storage = 20

# Cache
cache_node_type = "cache.t3.micro"      # Use cache.t3.small+ for production

# Container image (after building and pushing)
container_image = "123456789.dkr.ecr.us-east-1.amazonaws.com/therapy-rag:latest"
```

### 3. Initialize and Apply

```bash
# Initialize Terraform
terraform init

# Review the plan
terraform plan

# Apply (creates all resources)
terraform apply
```

### 4. Build and Push Docker Image

```bash
# Get ECR login
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin 123456789.dkr.ecr.us-east-1.amazonaws.com

# Build image
docker build -t therapy-rag .

# Tag for ECR
docker tag therapy-rag:latest 123456789.dkr.ecr.us-east-1.amazonaws.com/therapy-rag:latest

# Push
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/therapy-rag:latest
```

### 5. Configure Secrets

Store API keys in AWS Secrets Manager:

```bash
# Create secret for API keys
aws secretsmanager create-secret \
  --name therapy-rag/api-keys \
  --secret-string '{
    "DEEPGRAM_API_KEY": "your-key",
    "OPENAI_API_KEY": "your-key",
    "ANTHROPIC_API_KEY": "your-key"
  }'
```

### 6. Run Database Migrations

```bash
# Get the ALB DNS name
terraform output alb_dns_name

# SSH tunnel or use a bastion host to run migrations
# Or deploy a one-time migration task
```

## Environment-Specific Configuration

### Development

```hcl
environment         = "dev"
db_instance_class   = "db.t3.micro"
cache_node_type     = "cache.t3.micro"
api_desired_count   = 1
worker_desired_count = 1
```

### Production

```hcl
environment         = "prod"
db_instance_class   = "db.t3.medium"
cache_node_type     = "cache.t3.medium"
api_desired_count   = 2
worker_desired_count = 2
```

## Outputs

After applying, Terraform outputs:

```bash
terraform output

# alb_dns_name     = "therapy-rag-dev-alb-123456.us-east-1.elb.amazonaws.com"
# db_endpoint      = "therapy-rag-dev.xxxxx.us-east-1.rds.amazonaws.com"
# redis_endpoint   = "therapy-rag-dev.xxxxx.cache.amazonaws.com"
# s3_bucket_name   = "therapy-rag-dev-recordings"
```

## Cost Estimation (Dev Environment)

| Resource | Type | Monthly Cost (approx) |
|----------|------|----------------------|
| RDS | db.t3.micro | $15 |
| ElastiCache | cache.t3.micro | $12 |
| ECS Fargate | 256 CPU, 512 MB | $10 |
| ALB | Base + LCU | $20 |
| S3 | Storage + requests | $5 |
| **Total** | | **~$62/month** |

## Cleanup

```bash
# Destroy all resources
terraform destroy
```

## Troubleshooting

### ECS Tasks Not Starting

1. Check CloudWatch logs: `/ecs/therapy-rag-dev`
2. Verify secrets are accessible
3. Check security group rules

### Database Connection Issues

1. Verify RDS security group allows ECS
2. Check database credentials in Secrets Manager
3. Test connection from ECS task

### Health Check Failures

1. Check ALB target group health
2. Verify `/health` endpoint responds
3. Review ECS task logs

## Next Steps

- Set up CI/CD pipeline (see `.github/workflows/`)
- Configure custom domain with Route 53
- Set up CloudWatch alarms
- Enable RDS automated backups
