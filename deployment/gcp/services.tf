# 1. Private Cloud Run Query Service (FastAPI)
resource "google_cloud_run_v2_service" "api" {
  name                = "${var.environment}-tt-rag-parts"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"
  depends_on = [
    google_project_service.required,
    google_secret_manager_secret_version.database_url
  ]

  template {
    service_account                  = google_service_account.runtime.email
    timeout                          = "15s"
    max_instance_request_concurrency = 16

    scaling {
      min_instance_count = 0
      max_instance_count = 20
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.postgres.connection_name]
      }
    }

    containers {
      image = var.image
      ports { container_port = 8080 }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
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

      env {
        name  = "ARTIFACTS_GCS_BUCKET"
        value = google_storage_bucket.artifacts.name
      }

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_url.secret_id
            version = "latest"
          }
        }
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
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
  count    = var.invoker != "" ? 1 : 0
  location = google_cloud_run_v2_service.api.location
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = var.invoker
}

# 2. Cloud Run Job for Batch Ingestion & Offline Index Rebuild
resource "google_cloud_run_v2_job" "ingest" {
  name                = "${var.environment}-personal-rag-ingest"
  location            = var.region
  deletion_protection = false
  depends_on = [
    google_project_service.required,
    google_secret_manager_secret_version.database_url
  ]

  template {
    task_count = 1

    template {
      service_account = google_service_account.ingest.email
      timeout         = "1800s" # 30 minutes max for full corpus re-indexing

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.postgres.connection_name]
        }
      }

      containers {
        image = var.image

        resources {
          limits = {
            cpu    = "2"
            memory = "2Gi"
          }
        }

        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }

        env {
          name  = "ENVIRONMENT"
          value = var.environment
        }

        env {
          name  = "LOCATION"
          value = "global"
        }

        env {
          name  = "ARTIFACTS_GCS_BUCKET"
          value = google_storage_bucket.artifacts.name
        }

        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.database_url.secret_id
              version = "latest"
            }
          }
        }

        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }
    }
  }
}
