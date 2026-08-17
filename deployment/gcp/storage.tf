# Catalog bucket (environment-scoped)
resource "google_storage_bucket" "catalog" {
  name                        = "${var.project_id}-${var.environment}-catalog"
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

# Personal RAG Raw and Normalized Artifacts Bucket
resource "google_storage_bucket" "artifacts" {
  name                        = "${var.project_id}-${var.environment}-rag-artifacts"
  location                    = var.region
  uniform_bucket_level_access = true
  versioning { enabled = true }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      num_newer_versions = 5
      with_state         = "ARCHIVED"
    }
  }
}
