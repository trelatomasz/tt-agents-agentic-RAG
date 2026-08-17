# GCP Project Bootstrap & Initial Deployment Guide

This document outlines the step-by-step procedure to bootstrap a new Google Cloud Platform (GCP) project, configure local environment variables, provision infrastructure via OpenTofu, and set up GitHub Actions Workload Identity Federation (WIF) for continuous deployment.

---

## 1. Local Environment Configuration

### A. OpenTofu Variables (`deployment/gcp/terraform.tfvars`)
Create a local `terraform.tfvars` file inside `deployment/gcp/` (this file is gitignored):

```hcl
project_id        = "tt-rag-505805"
region            = "europe-west1"
environment       = "dev"
image             = "europe-west1-docker.pkg.dev/tt-rag-505805/tt-rag-parts/api:latest"
invoker           = "user:pikson.tom@gmail.com"
github_repository = "trelatomasz/tt-agents-agentic-RAG"
db_tier           = "db-f1-micro"
db_name           = "personal_rag"
db_user           = "rag_app"
```

### B. Application Environment (`.env`)
Create a `.env` file in the project root for local development and testing (gitignored):

```properties
PROJECT_ID=tt-rag-505805
LOCATION=global
MODEL_ID=gemini-2.5-flash
CATALOG_PATH=data/catalog.json
USE_VERTEX=false
```

---

## 2. Step-by-Step Initial Project Bootstrap

Execute these commands from your terminal (or WSL shell if using Windows):

### Step 1: Authenticate with Google Cloud
Ensure your local `gcloud` CLI session is active and targeting your project:

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project tt-rag-505805
```

---

### Step 2: Build & Push the Initial Container Image
Cloud Run requires an initial image in Artifact Registry before provisioning the service.

1. **Enable required bootstrap APIs**:
   ```bash
   gcloud services enable \
     artifactregistry.googleapis.com \
     cloudbuild.googleapis.com \
     --project=tt-rag-505805
   ```

2. **Create the Artifact Registry Docker repository**:
   ```bash
   gcloud artifacts repositories create tt-rag-parts \
     --repository-format=docker \
     --location=europe-west1 \
     --project=tt-rag-505805
   ```

3. **Build and push the image via Cloud Build**:
   ```bash
   gcloud builds submit \
     --project=tt-rag-505805 \
     --tag=europe-west1-docker.pkg.dev/tt-rag-505805/tt-rag-parts/api:latest \
     .
   ```

---

### Step 3: Provision Infrastructure with OpenTofu

1. **Initialize OpenTofu**:
   ```bash
   cd deployment/gcp
   tofu init
   ```

2. **Preview the execution plan**:
   ```bash
   tofu plan
   ```

3. **Apply the configuration**:
   ```bash
   tofu apply -auto-approve
   ```

OpenTofu will automatically provision:
- Cloud Run Query Service (`dev-tt-rag-parts`)
- Cloud Run Batch Ingestion Job (`dev-personal-rag-ingest`)
- Cloud SQL PostgreSQL 16 instance with `pgvector` enabled
- Secret Manager secrets for database credentials
- Versioned Cloud Storage buckets for catalog and artifacts
- Workload Identity Federation (WIF) pool, provider, and least-privilege service accounts

---

### Step 4: Configure GitHub Actions CI/CD Secrets & Variables

After OpenTofu finishes applying, retrieve the generated outputs:

```bash
tofu output wif_provider
tofu output wif_service_account
tofu output service_url
```

Navigate to your GitHub repository: **Settings $\rightarrow$ Secrets and variables $\rightarrow$ Actions**, and configure:

| Variable Name | Type | Value |
|---|---|---|
| `GCP_PROJECT_ID` | **Variable** | `tt-rag-505805` |
| `GCP_REGION` | **Variable** | `europe-west1` |
| `GCP_WIF_PROVIDER` | **Variable** | Output from `tofu output wif_provider` |
| `GCP_WIF_SERVICE_ACCOUNT` | **Variable** | Output from `tofu output wif_service_account` |
| `GCP_INVOKER` | **Variable** | *(Optional)* `user:pikson.tom@gmail.com` |

Once these variables are set, every `git push` to `main` (production) or `develop` (dev) will build, test, and deploy automatically without static service account keys!

---

### Step 5: Post-Deployment Smoke Test

Verify that your newly deployed service is healthy:

```bash
# Execute the smoke test script
./scripts/smoke.sh
```

Or query the endpoint directly with an identity token:

```bash
SERVICE_URL=$(tofu -chdir=deployment/gcp output -raw service_url)
TOKEN=$(gcloud auth print-identity-token)
curl -H "Authorization: Bearer ${TOKEN}" "${SERVICE_URL}/health"
```
