resource "google_iam_workload_identity_pool" "github" {
  count                     = var.github_repository != "" ? 1 : 0
  workload_identity_pool_id = "github-pool-${var.environment}"
  display_name              = "GitHub Actions Pool (${var.environment})"
  description               = "Workload Identity Pool for GitHub Actions CI/CD workflows"
  depends_on                = [google_project_service.required]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  count                              = var.github_repository != "" ? 1 : 0
  workload_identity_pool_id          = google_iam_workload_identity_pool.github[0].workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider-${var.environment}"
  display_name                       = "GitHub Actions Provider (${var.environment})"
  description                        = "OIDC Provider for GitHub Actions"

  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.actor"            = "assertion.actor"
    "attribute.repository"       = "assertion.repository"
    "attribute.repository_owner" = "assertion.repository_owner"
  }

  attribute_condition = "assertion.repository == '${var.github_repository}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "wif_deployer" {
  count              = var.github_repository != "" ? 1 : 0
  service_account_id = google_service_account.github_deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github[0].name}/attribute.repository/${var.github_repository}"
}
