# Smart Campus Digital Twin — development helpers
# Requires: docker, docker-compose, python >= 3.12, kcat (optional)

.PHONY: help env up down dev logs ps build test lint clean ml-train ml-status ml-prediction-logs ml-prediction-restart ml-retrain-logs frontend-update frontend-build frontend-up

COMPOSE      = docker compose -f docker-compose.yml
COMPOSE_DEV  = docker compose -f docker-compose.dev.yml
PYTHON       = python3

##@ Setup

env: ## Copy .env.example files to .env (safe defaults, fill in real secrets)
	@for f in env/*.env.example; do \
		dest="$${f%.example}"; \
		if [ ! -f "$$dest" ]; then \
			cp "$$f" "$$dest"; \
			echo "Created $$dest (edit with real values)"; \
		else \
			echo "Skipped $$dest (already exists)"; \
		fi; \
	done

##@ Full stack

up: ## Start all services (full pipeline)
	$(COMPOSE) up -d

down: ## Stop and remove all containers (data volumes preserved)
	$(COMPOSE) down

build: ## Rebuild all custom images
	$(COMPOSE) build

logs: ## Tail logs for all services
	$(COMPOSE) logs -f

ps: ## Show running containers and health
	$(COMPOSE) ps

##@ Machine Learning

ml-train: ## Run one-shot retrain (canteen, library, energy) against running MLflow
	$(COMPOSE) run --rm ml-retrain python retrain.py

ml-status: ## Show current Production model versions in MLflow
	$(COMPOSE) run --rm ml-retrain \
		python -c "\
import mlflow, os; \
mlflow.set_tracking_uri(os.environ.get('MLFLOW_TRACKING_URI','http://mlflow:5000')); \
client = mlflow.tracking.MlflowClient(); \
[print(f'  {m}: v{v.version}  run={v.run_id[:8]}') \
 for m in ['campus_canteen_congestion','campus_library_congestion','campus_energy_forecast'] \
 for v in (client.get_latest_versions(m, stages=['Production']) or [{'version':'NONE','run_id':''}])]\
"

ml-prediction-logs: ## Tail logs from ML prediction service
	docker logs -f campus-ml-prediction

ml-retrain-logs: ## Tail logs from ML retrain scheduler
	docker logs -f campus-ml-retrain

ml-prediction-restart: ## Restart ML prediction service (reload models)
	$(COMPOSE) restart ml-prediction
	@echo "Waiting for service to be healthy..."
	@sleep 5
	@curl -s http://localhost:8001/health | python3 -m json.tool

##@ Frontend (Three.js / Next.js — git submodule: frontend/)

frontend-update: ## Pull latest commits from the frontend submodule
	git submodule update --remote --merge frontend
	@echo "  Submodule updated. Run 'make frontend-build' to rebuild the image."

frontend-build: ## Rebuild only the frontend Docker image
	$(COMPOSE) build frontend

frontend-up: ## Start only the frontend container (api must already be running)
	$(COMPOSE) up -d frontend
	@echo ""
	@echo "  Three.js dashboard → http://localhost:3001"

##@ Dev (minimal — broker + databases only, run services on host)

dev: ## Start only broker + databases (simulator runs on host)
	$(COMPOSE_DEV) up -d
	@echo ""
	@echo "  MQTT     → localhost:1883"
	@echo "  InfluxDB → http://localhost:8086"
	@echo "  Postgres → localhost:5432"
	@echo ""
	@echo "  Run the simulator: python -m simulator.main"

dev-down: ## Stop dev stack
	$(COMPOSE_DEV) down

##@ Testing

test: ## Run all unit tests
	$(PYTHON) -m pytest tests/ -v

test-schemas: ## Test shared schemas only (fast, no infra needed)
	$(PYTHON) -m pytest tests/unit/test_schemas.py -v

##@ Code quality

lint: ## Run ruff linter across all Python code
	ruff check .

format: ## Auto-format with ruff
	ruff format .

##@ Utilities

kafka-topics: ## List Kafka topics
	docker exec campus-kafka kafka-topics.sh --bootstrap-server localhost:9092 --list

kafka-tail: ## Tail a topic (TOPIC=sensors.temperature make kafka-tail)
	kcat -b localhost:9092 -t $(TOPIC) -C -o end

influx-query: ## Open InfluxDB Data Explorer in browser
	open http://localhost:8086

clean: ## Remove Python cache files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

.DEFAULT_GOAL := help
