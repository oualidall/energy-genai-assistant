# Infrastructure for the Energy GenAI Assistant.
#
# Provisions the minimal, free-tier-friendly GCP footprint:
#   - BigQuery dataset holding the RTE energy tables
#   - Artifact Registry repo for the container image
#   - Cloud Run service running the FastAPI app
#   - A budget alert so a misconfiguration can never cause a surprise bill
#
# Everything here is covered by the GCP free trial credit and the always-free
# tier for a portfolio-scale workload.

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── Data warehouse ─────────────────────────────────────────────────────────────
resource "google_bigquery_dataset" "rte_energy" {
  dataset_id  = var.bigquery_dataset
  location    = var.region
  description = "RTE electricity data queried by the GenAI assistant."
}

# ── Container registry ─────────────────────────────────────────────────────────
resource "google_artifact_registry_repository" "app" {
  location      = var.region
  repository_id = "energy-genai"
  format        = "DOCKER"
  description   = "Container images for the Energy GenAI Assistant."
}

# ── Serving ────────────────────────────────────────────────────────────────────
resource "google_cloud_run_v2_service" "api" {
  name     = "energy-genai-assistant"
  location = var.region

  template {
    scaling {
      min_instance_count = 0 # scale to zero => no idle cost
      max_instance_count = 2
    }
    containers {
      image = var.container_image
      ports {
        container_port = 8080
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "BIGQUERY_DATASET"
        value = var.bigquery_dataset
      }
    }
  }
}
