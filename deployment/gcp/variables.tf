variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region for all regional resources"
  type        = string
  default     = "europe-west1"
}

variable "environment" {
  description = "Deployment environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "image" {
  description = "Container image URI for Cloud Run API service and jobs"
  type        = string
}

variable "invoker" {
  description = "IAM member allowed to invoke the private Cloud Run API service (e.g. user:name@example.com or allAuthenticatedUsers)"
  type        = string
  default     = ""
}

variable "github_repository" {
  description = "GitHub repository in 'owner/repo' format permitted to authenticate via Workload Identity Federation"
  type        = string
  default     = ""
}

variable "db_tier" {
  description = "Cloud SQL machine tier for PostgreSQL (e.g. db-f1-micro for dev, db-custom-2-7680 for prod)"
  type        = string
  default     = "db-f1-micro"
}

variable "db_name" {
  description = "PostgreSQL database name for personal RAG"
  type        = string
  default     = "personal_rag"
}

variable "db_user" {
  description = "PostgreSQL username for application runtime"
  type        = string
  default     = "rag_app"
}
