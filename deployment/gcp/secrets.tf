resource "google_secret_manager_secret" "db_password" {
  secret_id = "${var.environment}-rag-db-password"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db_password.result
}

resource "google_secret_manager_secret" "database_url" {
  secret_id = "${var.environment}-rag-database-url"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_version" "database_url" {
  secret      = google_secret_manager_secret.database_url.id
  secret_data = "postgresql://${google_sql_user.rag_user.name}:${random_password.db_password.result}@/${google_sql_database.rag_db.name}?host=/cloudsql/${google_sql_database_instance.postgres.connection_name}"
}
