terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

variable "project"     {}
variable "region"      { default = "europe-west1" }
variable "environment" { default = "production" }

provider "google" {
  project = var.project
  region  = var.region
}

# GCS Data Lake
resource "google_storage_bucket" "data_lake" {
  name          = "${var.project}-datasphere-${var.environment}"
  location      = upper(var.region)
  force_destroy = var.environment != "production"

  versioning { enabled = true }

  lifecycle_rule {
    action { type = "AbortIncompleteMultipartUpload" }
    condition { age = 1 }
  }
}

# BigQuery Dataset
resource "google_bigquery_dataset" "main" {
  dataset_id  = "datasphere"
  location    = upper(var.region)
  description = "DataSphere main dataset"
}

# Cloud Run for services
resource "google_cloud_run_v2_service" "datasphere_api" {
  name     = "datasphere-api-${var.environment}"
  location = var.region

  template {
    containers {
      image = "gcr.io/${var.project}/datasphere-api:latest"
      resources {
        limits = { cpu = "2", memory = "2Gi" }
      }
    }
  }
}

output "data_lake_bucket" { value = google_storage_bucket.data_lake.name }
output "bigquery_dataset"  { value = google_bigquery_dataset.main.dataset_id }
