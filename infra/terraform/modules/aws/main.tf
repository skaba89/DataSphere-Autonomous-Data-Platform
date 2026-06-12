terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "region"       { default = "eu-west-1" }
variable "project_name" { default = "datasphere" }
variable "environment"  { default = "production" }

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# VPC
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${var.project_name}-${var.environment}"
  cidr = "10.0.0.0/16"

  azs             = ["${var.region}a", "${var.region}b", "${var.region}c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = var.environment != "production"
}

# S3 Data Lake
resource "aws_s3_bucket" "data_lake" {
  bucket = "${var.project_name}-data-lake-${var.environment}"
}

resource "aws_s3_bucket_versioning" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "aws:kms" }
  }
}

# Redshift
resource "aws_redshift_cluster" "main" {
  cluster_identifier  = "${var.project_name}-${var.environment}"
  database_name       = "datasphere"
  master_username     = "datasphere"
  master_password     = var.redshift_password
  node_type           = "dc2.large"
  cluster_type        = "single-node"
  skip_final_snapshot = var.environment != "production"

  vpc_security_group_ids = [aws_security_group.redshift.id]
}

variable "redshift_password" {
  sensitive = true
}

resource "aws_security_group" "redshift" {
  name   = "${var.project_name}-redshift-${var.environment}"
  vpc_id = module.vpc.vpc_id

  ingress {
    from_port   = 5439
    to_port     = 5439
    protocol    = "tcp"
    cidr_blocks = module.vpc.private_subnets_cidr_blocks
  }
}

output "data_lake_bucket" { value = aws_s3_bucket.data_lake.bucket }
output "redshift_endpoint" { value = aws_redshift_cluster.main.endpoint }
