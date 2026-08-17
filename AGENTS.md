# Repository Security & Privacy Rules

> **CRITICAL MANDATE: ZERO IDENTITY OR CREDENTIAL LEAKS**
> This repository is **100% PUBLIC**. Under NO circumstances may any personal identity, account email, real GCP Project ID, billing info, private key, token, or secret ever be written to files, committed to git, or included in pull requests.

---

## 1. Absolute Redaction Rules

1. **GCP Project Identifiers**:
   - Never write real GCP project IDs (e.g., `tt-rag-...`).
   - Always use generic placeholders: `your-gcp-project-id`, `PROJECT_ID`, or `${var.project_id}`.

2. **Personal Identifiers & Emails**:
   - Never write personal or organizational emails (e.g., `@gmail.com`, real user emails).
   - Always use generic placeholders: `user:your-email@example.com` or `your-email@example.com`.

3. **Service Account Names & WIF Providers**:
   - Never commit specific WIF pool IDs, provider resource paths, or organization numbers.
   - Use `${var.wif_provider}` or `projects/1234567890/locations/global/workloadIdentityPools/...` placeholders.

4. **Secrets & Credentials**:
   - Zero hardcoded API keys (`AIza...`, `ghp_...`, `gho_...`, `ya29...`, `Bearer ...`).
   - Zero hardcoded passwords, tokens, certificates, or private keys.

---

## 2. File & Commit Hygiene

1. **Gitignore Strict Enforcement**:
   - Never remove or bypass `.gitignore` rules for `.env`, `*.tfvars`, `*.tfstate`, `*credentials*.json`, `*sa_key*.json`, `*.pem`, `*.key`.
   - Always verify files being committed with `git status` before committing.

2. **Examples Only**:
   - Only check in sanitized `.env.example` and `terraform.tfvars.example`.
   - Never stage or commit `.env` or `deployment/gcp/terraform.tfvars`.

3. **Pre-Commit Verification**:
   - Run a sensitive pattern scan before pushing or proposing changes.
   - Any accidental commit of private details must be immediately wiped from history before pushing.

---

## 3. GitHub Actions & CI Policy

1. **Secrets vs Variables**:
   - All environment-specific identifiers (`GCP_PROJECT_ID`, `GCP_WIF_PROVIDER`, etc.) must be referenced as GitHub **Secrets** (`${{ secrets.GCP_PROJECT_ID }}`) or masked dynamically so they are never printed to public build logs.
2. **Pull Requests**:
   - All PRs targeting `main` must strictly come from `dev`.
   - All PRs targeting `dev` must come from feature branches.
   - Direct pushes to `main` and `dev` are strictly forbidden.
