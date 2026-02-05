terraform {
  # For local development, use local backend
  # Switch to S3 backend when deploying to AWS:
  #
  # backend "s3" {
  #   bucket         = "therapy-rag-terraform-state"
  #   key            = "dev/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "therapy-rag-terraform-locks"
  #   encrypt        = true
  # }

  backend "local" {
    path = "terraform.tfstate"
  }
}
