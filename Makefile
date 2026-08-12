PYTHONPATH := src
PROJECT_ID ?= gen-lang-client-0465666778
REGION ?= europe-west1
IMAGE ?= $(REGION)-docker.pkg.dev/$(PROJECT_ID)/gpc-parts-rag/api:$(shell git rev-parse --short HEAD)

.PHONY: sync test eval lint image plan deploy smoke
sync:
	uv sync
test:
	uv run pytest -q
eval:
	PYTHONPATH=src uv run python evals/run_eval.py
lint:
	uv run ruff check src tests evals
image:
	gcloud builds submit --tag $(IMAGE) .
plan:
	tofu -chdir=deployment/gcp plan -var='project_id=$(PROJECT_ID)' -var='region=$(REGION)' -var='image=$(IMAGE)' -var='invoker=user:your-email@example.com'
deploy:
	tofu -chdir=deployment/gcp apply -auto-approve -var='project_id=$(PROJECT_ID)' -var='region=$(REGION)' -var='image=$(IMAGE)' -var='invoker=user:your-email@example.com'
smoke:
	./scripts/smoke.sh
