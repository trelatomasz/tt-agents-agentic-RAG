PYTHONPATH := src
PROJECT_ID ?= $(shell gcloud config get-value project 2>/dev/null)
REGION ?= europe-west1
ENVIRONMENT ?= dev
INVOKER ?= user:$(shell gcloud config get-value account 2>/dev/null)
IMAGE ?= $(REGION)-docker.pkg.dev/$(PROJECT_ID)/tt-rag-parts/api:$(shell git rev-parse --short HEAD)

.PHONY: sync test eval demo lint image plan deploy smoke
sync:
	uv sync
test:
	uv run pytest -q
eval:
	PYTHONPATH=src uv run python evals/run_eval.py
demo:
	PYTHONPATH=src uv run python scripts/personal_rag_demo.py
lint:
	uv run ruff check src tests evals scripts
image:
	gcloud builds submit --tag $(IMAGE) .
plan:
	tofu -chdir=deployment/gcp plan -var='project_id=$(PROJECT_ID)' -var='region=$(REGION)' -var='environment=$(ENVIRONMENT)' -var='image=$(IMAGE)' -var='invoker=$(INVOKER)'
deploy:
	tofu -chdir=deployment/gcp apply -auto-approve -var='project_id=$(PROJECT_ID)' -var='region=$(REGION)' -var='environment=$(ENVIRONMENT)' -var='image=$(IMAGE)' -var='invoker=$(INVOKER)'
smoke:
	./scripts/smoke.sh
