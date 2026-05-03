# TherapyRAG — AWS Terraform module

HIPAA-aware deployment of the TherapyRAG backend on AWS: VPC + RDS Postgres 16
with pgvector + ElastiCache Redis + ECS Fargate (app + worker) behind an ALB,
with Secrets Manager, KMS-encrypted S3 for recordings, ACM + Route53, and
CloudWatch alarms routed to SNS email.

Fly.io remains the default deploy target (`/fly.toml` at the repo root). This
module exists for prospects that require AWS under their own Business
Associate Addendum.

## Prerequisites

- Terraform `~> 1.9`
- AWS CLI v2, authenticated with credentials that can create VPC, RDS,
  ElastiCache, ECS, IAM, ACM, Route53, Secrets Manager, KMS, S3, CloudWatch
  and SNS resources.
- A Route53 hosted zone that owns `var.domain_name`.
- A signed BAA on your AWS account. See `../../LAUNCH_READINESS.md` for the
  BAA checklist.
- An ECR repository containing the app image (same image may serve as worker).
- Remote state bootstrap: an S3 bucket and DynamoDB lock table created ahead
  of time, then reference them in `backend.tf` (see `backend.tf.example`).

## Apply recipe

```bash
cd infra/aws

cp backend.tf.example backend.tf         # fill in bucket and table names
cp terraform.tfvars.example terraform.tfvars  # fill in the variables

terraform init
terraform plan -out=tf.plan
terraform apply tf.plan
```

First apply takes ~20-30 minutes — RDS multi-AZ and ElastiCache provisioning
dominate.

## Post-apply steps

### 1. Enable the `pgvector` extension

The `shared_preload_libraries` parameter already loads `pgvector`, but the
extension itself must be created once per database:

```bash
PGPASSWORD=$(aws secretsmanager get-secret-value \
  --secret-id therapyrag-prod/DATABASE_URL \
  --query SecretString --output text | jq -r 'split("://")[1] | split(":")[1] | split("@")[0]')

psql "postgres://therapyrag@<rds_endpoint>:5432/therapyrag?sslmode=require" \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

(Or use the `postgresql` Terraform provider — we opted out to keep the
provider count and the bootstrap complexity down.)

### 2. Populate Secrets Manager

Terraform seeds each secret with the placeholder string
`REPLACE_VIA_PUT_SECRET_VALUE` and then ignores future changes to the value.
Populate each one with a real value:

```bash
PREFIX=therapyrag-prod

# DATABASE_URL — built from the RDS outputs + master password
DB_HOST=$(terraform output -raw rds_endpoint)
DB_PWD="<fetched from RDS console or rotated master credential>"
aws secretsmanager put-secret-value \
  --secret-id "$PREFIX/DATABASE_URL" \
  --secret-string "postgresql+asyncpg://therapyrag:$DB_PWD@$DB_HOST/therapyrag?ssl=require"

# App secrets
for name in JWT_SECRET TOTP_ENCRYPTION_KEY; do
  aws secretsmanager put-secret-value \
    --secret-id "$PREFIX/$name" \
    --secret-string "$(openssl rand -base64 48)"
done

# Third-party API keys
aws secretsmanager put-secret-value --secret-id "$PREFIX/ANTHROPIC_API_KEY"   --secret-string "sk-ant-..."
aws secretsmanager put-secret-value --secret-id "$PREFIX/OPENAI_API_KEY"      --secret-string "sk-..."
aws secretsmanager put-secret-value --secret-id "$PREFIX/DEEPGRAM_API_KEY"    --secret-string "..."
aws secretsmanager put-secret-value --secret-id "$PREFIX/STRIPE_SECRET_KEY"   --secret-string "sk_live_..."
aws secretsmanager put-secret-value --secret-id "$PREFIX/STRIPE_WEBHOOK_SECRET" --secret-string "whsec_..."
aws secretsmanager put-secret-value --secret-id "$PREFIX/STRIPE_PRICE_ID"     --secret-string "price_..."
aws secretsmanager put-secret-value --secret-id "$PREFIX/RESEND_API_KEY"      --secret-string "re_..."
aws secretsmanager put-secret-value --secret-id "$PREFIX/SENTRY_DSN"          --secret-string "https://...@sentry.io/..."
```

After updating `DATABASE_URL`, force a new ECS deployment so tasks pick up the
new value:

```bash
aws ecs update-service \
  --cluster "$PREFIX-cluster" \
  --service "$PREFIX-app" \
  --force-new-deployment
aws ecs update-service \
  --cluster "$PREFIX-cluster" \
  --service "$PREFIX-worker" \
  --force-new-deployment
```

### 3. Confirm the SNS email subscription

Check the inbox for `var.alert_email` and accept the confirmation link
Amazon sends.

### 4. Run Alembic migrations

From a workstation with network access to the RDS endpoint (e.g. over a VPN
or bastion):

```bash
DATABASE_URL=... uv run alembic upgrade head
```

## HA / cost upgrade path

The default wiring is cost-optimised. When moving to production traffic:

| Concern | Default | Upgrade |
| --- | --- | --- |
| NAT gateway | single, one AZ | set `single_nat_gateway = false` in `network.tf` (one NAT per AZ) |
| RDS | `db.t3.medium`, multi-AZ | bump to `db.m6g.large` or higher; consider read replica |
| Redis | single node `cache.t3.micro` | bump node count + `automatic_failover_enabled = true` and `multi_az_enabled = true` |
| ECS | pure FARGATE | FARGATE + FARGATE_SPOT mix already enabled at cluster level; adjust service capacity provider strategy |
| Log retention | 90 days | match compliance retention policy |

## Destroy recipe

```bash
# Break deletion protection first
aws rds modify-db-instance \
  --db-instance-identifier therapyrag-prod-db \
  --no-deletion-protection --apply-immediately

aws elbv2 modify-load-balancer-attributes \
  --load-balancer-arn "$(terraform output -raw alb_arn || true)" \
  --attributes Key=deletion_protection.enabled,Value=false

terraform destroy
```

Buckets with objects will block destroy — empty them first or set
`force_destroy = true` on the bucket resources for a non-production teardown.

## BAA confirmation checklist

Before directing PHI traffic at this stack, confirm every item below:

- [ ] AWS BAA countersigned on the target account.
  See `../../LAUNCH_READINESS.md` for the paperwork workflow.
- [ ] RDS `storage_encrypted = true` and multi-AZ in the `plan` output.
- [ ] S3 recordings bucket reports SSE-KMS and public access fully blocked.
- [ ] ALB has no HTTP listener serving traffic directly — only a 301 to HTTPS.
- [ ] `rds.force_ssl = 1` is applied (`aws rds describe-db-parameters`).
- [ ] CloudWatch SNS email confirmed.
- [ ] CloudTrail is enabled at the organisation or account level (outside
  this module; set up once per account).
- [ ] VPC flow logs visible in CloudWatch (`/aws/vpc/flow-logs/...`).

## Service inventory

- VPC `10.0.0.0/16`, 2x public `/20`, 2x private `/20`, 1 NAT gateway, IGW,
  flow logs to CloudWatch.
- RDS Postgres 16 (`db.t3.medium` default), multi-AZ, encrypted, 30-day
  backups, enhanced monitoring, Performance Insights.
- ElastiCache Redis 7 (`cache.t3.micro` default), TLS + auth token, at-rest
  and in-transit encryption.
- ECS Fargate cluster with app service (2 tasks) and worker service (1 task).
- ALB with HTTPS listener (TLS 1.3 policy), HTTP→HTTPS redirect, access logs
  to S3.
- ACM cert + Route53 A-record alias for `var.domain_name`.
- KMS-encrypted S3 recordings bucket (versioned, TLS-enforced, noncurrent
  versions expire after 30 days).
- Secrets Manager entries for every app-level credential.
- CloudWatch alarms: ALB 5xx rate > 1%, RDS CPU > 80% for 15 min, RDS free
  storage < 10%. All route to an SNS topic with `alert_email` subscribed.
