# Agent Guardian — developer task runner.
# All Python work goes through `uv` (the bare `python`/`py` are not on PATH here).
# Usage: `make <target>`. Run `make help` (or just `make`) to list targets.

# Use bash for recipes where available; harmless if make falls back.
SHELL := /bin/sh

# Overridable knobs:  make serve PORT=9000
PORT ?= 8000
WEB_PORT ?= 8080
WEB_HOST ?= 127.0.0.1
HOST ?= 0.0.0.0
IMAGE ?= agent-guardian:local
PYTEST_ARGS ?=
FRONTEND_DIR ?= frontend
NPM ?= npm --prefix $(FRONTEND_DIR)

# Cloud Run / Artifact Registry / GCS Artifacts
GCP_PROJECT          ?= imgcp-51c5a39739fbedcd
GCP_REGION           ?= us-central1
AR_REPO              ?= agent-guardian
ARTIFACT_BUCKET      ?= agentguardian-prod-artifacts
ARTIFACT_SERVICE_URI ?= gs://$(ARTIFACT_BUCKET)
BACKEND_IMG          := $(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT)/$(AR_REPO)/backend
FRONTEND_IMG         := $(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT)/$(AR_REPO)/frontend

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# --------------------------------------------------------------------------- #
# Environment
# --------------------------------------------------------------------------- #
.PHONY: install
install: ## Sync all dependencies (incl. dev) into the uv venv
	uv sync

.PHONY: install-prod
install-prod: ## Sync runtime dependencies only (no dev tools)
	uv sync --no-dev

.PHONY: install-all
install-all: install fe-install ## Install backend (uv) + frontend (npm) deps

.PHONY: lock
lock: ## Refresh uv.lock from pyproject.toml
	uv lock

# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
.PHONY: test
test: test-unit ## Default test run (fast, offline unit suite)

.PHONY: test-unit
test-unit: ## Run the unit suite (no network / credentials needed)
	uv run pytest tests/unit -q $(PYTEST_ARGS)

.PHONY: test-integration
test-integration: ## Run the integration suite
	uv run pytest tests/integration -q $(PYTEST_ARGS)

.PHONY: test-e2e
test-e2e: ## Run the end-to-end suite (may require live credentials)
	uv run pytest tests/e2e -q $(PYTEST_ARGS)

.PHONY: test-all
test-all: ## Run every test (unit + integration + e2e)
	uv run pytest tests -q $(PYTEST_ARGS)

.PHONY: smoke
smoke: ## Run the live double-review smoke test (needs configured env)
	uv run python scripts/run_agent_smoke_test.py

# --------------------------------------------------------------------------- #
# Quality
# --------------------------------------------------------------------------- #
.PHONY: format
format: ## Format source code using ruff
	uv run ruff format agent_guardian api tests

.PHONY: lint
lint: ## Static checks for unused imports / undefined names (pyflakes)
	uv run python -X utf8 -c "import os, sys, subprocess; files = [os.path.join(r, f) for r, _, fs in os.walk('agent_guardian') if 'skills' not in r.split(os.sep) for f in fs if f.endswith('.py')]; subprocess.run([sys.executable, '-X', 'utf8', '-m', 'pyflakes'] + files + ['api'], check=True)"





.PHONY: lint-ruff
lint-ruff: ## Lint check source code using ruff
	uv run ruff check agent_guardian api tests

.PHONY: security
security: ## Security scan of the source (bandit)
	uv run bandit -r agent_guardian api -ll

.PHONY: validate-skills
validate-skills: ## Validate the dynamic GCP / local skill loader
	uv run pytest tests/unit/test_dynamic_skills.py -q

.PHONY: check
check: format lint lint-ruff security test-unit ## Pre-commit gate: format + lint + security + unit tests

# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #
.PHONY: dev
dev: ## Run both backend (FastAPI :8000) and frontend (Next.js :3000) in dev mode
	uv run python -c "import subprocess, sys; p1 = subprocess.Popen(['uv', 'run', 'uvicorn', 'api.main:app', '--host', '$(HOST)', '--port', '$(PORT)', '--reload', '--reload-dir', 'agent_guardian', '--reload-dir', 'api']); p2 = subprocess.Popen(['npm', '--prefix', '$(FRONTEND_DIR)', 'run', 'dev'], shell=True); [p.wait() for p in (p1, p2)]"

.PHONY: start
start: ## Run both backend (FastAPI :8000) and frontend (Next.js :3000) production servers
	uv run python -c "import subprocess, sys; p1 = subprocess.Popen(['uv', 'run', 'uvicorn', 'api.main:app', '--host', '$(HOST)', '--port', '$(PORT)']); p2 = subprocess.Popen(['npm', '--prefix', '$(FRONTEND_DIR)', 'run', 'start'], shell=True); [p.wait() for p in (p1, p2)]"

.PHONY: serve
serve: ## Run the FastAPI service via uvicorn (PORT, default 8000)
	uv run uvicorn api.main:app --host $(HOST) --port $(PORT) --reload --reload-dir agent_guardian --reload-dir api

.PHONY: web
web: ## Run the ADK Web operator UI (WEB_PORT, default 8080)
	bash scripts/run_adk_web.sh --host $(WEB_HOST) --port $(WEB_PORT)

# --------------------------------------------------------------------------- #
# Frontend (Next.js, in $(FRONTEND_DIR))
# --------------------------------------------------------------------------- #
.PHONY: fe-install
fe-install: ## Install frontend deps from package-lock.json (npm ci)
	$(NPM) ci

.PHONY: fe-dev
fe-dev: ## Run the Next.js dev server (next dev)
	$(NPM) run dev

.PHONY: fe-build
fe-build: ## Production build of the frontend (next build)
	$(NPM) run build

.PHONY: fe-start
fe-start: ## Serve the production build (next start)
	$(NPM) run start

.PHONY: fe-clean
fe-clean: ## Remove frontend node_modules and the .next build cache
	uv run python -c "import shutil; shutil.rmtree('$(FRONTEND_DIR)/node_modules', ignore_errors=True); shutil.rmtree('$(FRONTEND_DIR)/.next', ignore_errors=True)"

# --------------------------------------------------------------------------- #
# Docker
# --------------------------------------------------------------------------- #
.PHONY: docker-build
docker-build: ## Build the container image ($(IMAGE))
	docker build -t $(IMAGE) .

.PHONY: docker-run
docker-run: ## Run the container, mapping PORT to the in-container 8080
	docker run --rm -p $(PORT):8080 --env-file .env $(IMAGE)

.PHONY: docker-build-backend
docker-build-backend: ## Build backend image for Cloud Run
	docker build -t $(BACKEND_IMG):latest .

.PHONY: docker-build-frontend
docker-build-frontend: ## Build frontend image for Cloud Run
	docker build -t $(FRONTEND_IMG):latest $(FRONTEND_DIR)

.PHONY: setup-gcs-artifacts
setup-gcs-artifacts: ## Provision the GCS bucket for ADK artifacts storage
	gcloud storage buckets create gs://$(ARTIFACT_BUCKET) --project=$(GCP_PROJECT) --location=$(GCP_REGION) --uniform-bucket-level-access || true

.PHONY: deploy-backend
deploy-backend: ## Build via Cloud Build and deploy backend to upskilling-agent-service
	gcloud builds submit --tag $(BACKEND_IMG):latest --project $(GCP_PROJECT) .
	gcloud run deploy upskilling-agent-service \
		--image $(BACKEND_IMG):latest \
		--command="" \
		--args="" \
		--region $(GCP_REGION) \
		--project $(GCP_PROJECT) \
		--update-env-vars "SESSION_SERVICE_URI=agentengine://projects/$(GCP_PROJECT)/locations/$(GCP_REGION)/reasoningEngines/6839756721917788160,ARTIFACT_SERVICE_URI=$(ARTIFACT_SERVICE_URI),ENABLE_CLOUD_TRACING=true,OTEL_SERVICE_NAME=agent-guardian,OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_agent_spans,GOOGLE_CLOUD_PROJECT=$(GCP_PROJECT),GOOGLE_CLOUD_LOCATION=global,SESSION_LOCATION=$(GCP_REGION),GOOGLE_CLOUD_AGENT_ENGINE_LOCATION=$(GCP_REGION)"

.PHONY: deploy-frontend
deploy-frontend: ## Build via Cloud Build and deploy frontend to upskilling-agent-service-frontend
	gcloud builds submit --tag $(FRONTEND_IMG):latest --project $(GCP_PROJECT) $(FRONTEND_DIR)
	gcloud run deploy upskilling-agent-service-frontend \
		--image $(FRONTEND_IMG):latest \
		--region $(GCP_REGION) \
		--project $(GCP_PROJECT)

# --------------------------------------------------------------------------- #
# Housekeeping
# --------------------------------------------------------------------------- #
.PHONY: clean
clean: ## Remove __pycache__, .pyc and pytest caches (cross-platform)
	uv run python -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]; [p.unlink() for p in pathlib.Path('.').rglob('*.pyc')]; shutil.rmtree('.pytest_cache', ignore_errors=True)"
