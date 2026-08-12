terraform {
  required_version = ">= 1.8"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
}

variable "project_id" { type = string }
variable "image" { type = string }
variable "invoker" { type = string }
variable "region" {
  type    = string
  default = "europe-west1"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  services = toset([
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "run.googleapis.com",
  ])
}

resource "google_project_service" "required" {
  for_each           = local.services
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "app" {
  location      = var.region
  repository_id = "gpc-parts-rag"
  format        = "DOCKER"
  depends_on    = [google_project_service.required]
}

resource "google_storage_bucket" "catalog" {
  name                        = "${var.project_id}-gpc-parts-catalog"
  location                    = var.region
  uniform_bucket_level_access = true
  versioning { enabled = true }
}

resource "google_storage_bucket_object" "catalog" {
  name         = "catalog/current.json"
  bucket       = google_storage_bucket.catalog.name
  source       = "${path.module}/../../data/catalog.json"
  content_type = "application/json"
}

resource "google_service_account" "runtime" {
  account_id   = "gpc-parts-rag-runtime"
  display_name = "GPC parts RAG runtime"
}

resource "google_project_iam_member" "vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_storage_bucket_iam_member" "catalog_reader" {
  bucket = google_storage_bucket.catalog.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_cloud_run_v2_service" "api" {
  name                = "gpc-parts-rag"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"
  depends_on          = [google_project_service.required]

  template {
    service_account                  = google_service_account.runtime.email
    timeout                          = "15s"
    max_instance_request_concurrency = 16
    scaling {
      min_instance_count = 0
      max_instance_count = 20
    }
    containers {
      image = var.image
      ports { container_port = 8080 }
      resources { limits = { cpu = "1", memory = "512Mi" } }
      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "LOCATION"
        value = "global"
      }
      env {
        name  = "USE_VERTEX"
        value = "true"
      }
      env {
        name  = "CATALOG_GCS_URI"
        value = "gs://${google_storage_bucket.catalog.name}/${google_storage_bucket_object.catalog.name}"
      }
      env {
        name  = "CATALOG_MAX_AGE_SECONDS"
        value = "86400"
      }
      startup_probe {
        http_get { path = "/health" }
        initial_delay_seconds = 1
        timeout_seconds       = 2
        period_seconds        = 3
        failure_threshold     = 10
      }
      liveness_probe {
        http_get { path = "/health" }
        timeout_seconds   = 2
        period_seconds    = 30
        failure_threshold = 3
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "invoker" {
  location = google_cloud_run_v2_service.api.location
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = var.invoker
}

output "service_url" { value = google_cloud_run_v2_service.api.uri }
output "catalog_uri" { value = "gs://${google_storage_bucket.catalog.name}/${google_storage_bucket_object.catalog.name}" }
