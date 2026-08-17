output "service_url" {
  description = "URL of the deployed Cloud Run query service"
  value       = google_cloud_run_v2_service.api.uri
}

output "catalog_uri" {
  description = "GCS URI of the legacy parts catalog"
  value       = "gs://${google_storage_bucket.catalog.name}/${google_storage_bucket_object.catalog.name}"
}

output "artifacts_bucket" {
  description = "GCS bucket for raw and normalized Personal RAG artifacts"
  value       = google_storage_bucket.artifacts.name
}

output "db_instance_connection_name" {
  description = "Cloud SQL PostgreSQL instance connection name for Cloud SQL Auth Proxy"
  value       = google_sql_database_instance.postgres.connection_name
}

output "wif_provider" {
  description = "Workload Identity Provider resource name for GitHub Actions auth"
  value       = length(google_iam_workload_identity_pool_provider.github) > 0 ? google_iam_workload_identity_pool_provider.github[0].name : ""
}

output "wif_service_account" {
  description = "Service account email for GitHub Actions deployer"
  value       = google_service_account.github_deployer.email
}
