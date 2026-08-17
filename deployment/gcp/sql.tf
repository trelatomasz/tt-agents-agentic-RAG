resource "random_password" "db_password" {
  length  = 24
  special = false
}

resource "random_id" "db_suffix" {
  byte_length = 4
}

resource "google_sql_database_instance" "postgres" {
  name                = "${var.environment}-rag-db-${random_id.db_suffix.hex}"
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = false

  settings {
    tier              = var.db_tier
    availability_type = "ZONAL"

    database_flags {
      name  = "cloudsql.enable_pgvector"
      value = "on"
    }

    backup_configuration {
      enabled    = true
      start_time = "02:00"
    }

    ip_configuration {
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }

    insights_config {
      query_insights_enabled  = true
      query_string_length     = 1024
      record_application_tags = true
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_sql_database" "rag_db" {
  name     = "${var.environment}_${var.db_name}"
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "rag_user" {
  name     = var.db_user
  instance = google_sql_database_instance.postgres.name
  password = random_password.db_password.result
}
