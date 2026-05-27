.PHONY: verify start stop logs build publish-testpypi publish-pypi clean chaos help

# Identify the virtual environment if it exists
PYTHON = .venv/bin/python
PYTEST = .venv/bin/pytest
RUFF = .venv/bin/ruff
MYPY = .venv/bin/mypy

help: ## Show this help screen
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

verify-helm: ## Verify Kubernetes Helm chart syntax and rendering
	@if command -v helm >/dev/null 2>&1; then \
		echo "=> Linting Helm charts..."; \
		helm lint charts/synapse; \
		echo "=> Templating Helm charts..."; \
		helm template test-edge charts/synapse > /dev/null; \
		echo "=> Helm charts are valid."; \
	else \
		echo "=> helm not found, skipping Helm verification."; \
	fi

verify: verify-helm ## Run the complete test suite, linting, type checking, and chaos
	@echo "=> Applying automatic linting fixes and formatting (ruff)..."
	$(RUFF) check --fix src tests tools
	$(RUFF) format src tests tools
	@echo "=> Running tests (pytest)..."
	$(PYTEST) tests/
	@echo "=> Running type checking (mypy)..."
	$(MYPY) src
	@echo "=> Running chaos smoke test integration..."
	$(MAKE) test-chaos
	@echo "=> Verification complete. The codebase is ready for release."

start: ## Start the P2P Mesh network in the background
	@PODMAN_COMPOSE_WARNING_LOGS=false docker compose -f docker/docker-compose.yml up -d --build --remove-orphans

stop: ## Stop the P2P network containers
	@PODMAN_COMPOSE_WARNING_LOGS=false docker compose -f docker/docker-compose.yml down

logs: ## Show the container logs in real time
	@PODMAN_COMPOSE_WARNING_LOGS=false docker compose -f docker/docker-compose.yml logs -f

chaos: ## Start the Chaos Monkey via docker compose to stress test the network
	@DOCKER_SOCK=$${DOCKER_SOCK:-/var/run/docker.sock}; \
	if [ "$$DOCKER_SOCK" = "/var/run/docker.sock" ] && command -v podman >/dev/null 2>&1; then \
		UID_VAL=$$(id -u); \
		if [ -S "/run/user/$$UID_VAL/podman/podman.sock" ]; then \
			DOCKER_SOCK="/run/user/$$UID_VAL/podman/podman.sock"; \
			echo "=> Detected rootless Podman. Using socket $$DOCKER_SOCK"; \
		fi; \
	fi; \
	DOCKER_SOCK=$$DOCKER_SOCK PODMAN_COMPOSE_WARNING_LOGS=false docker compose -f docker/docker-compose.yml --profile tools up -d --build --remove-orphans chaos

chaos-network: ## Start network chaos injection (latency & packet loss) via Pumba
	@DOCKER_SOCK=$${DOCKER_SOCK:-/var/run/docker.sock}; \
	if [ "$$DOCKER_SOCK" = "/var/run/docker.sock" ] && command -v podman >/dev/null 2>&1; then \
		UID_VAL=$$(id -u); \
		if [ -S "/run/user/$$UID_VAL/podman/podman.sock" ]; then \
			DOCKER_SOCK="/run/user/$$UID_VAL/podman/podman.sock"; \
			echo "=> Detected rootless Podman. Using socket $$DOCKER_SOCK"; \
		fi; \
	fi; \
	DOCKER_SOCK=$$DOCKER_SOCK PODMAN_COMPOSE_WARNING_LOGS=false docker compose -f docker/docker-compose.yml --profile tools up -d --remove-orphans pumba

chaos-network-stop: ## Stop Pumba network chaos container and restore network stability
	@PODMAN_COMPOSE_WARNING_LOGS=false docker compose -f docker/docker-compose.yml --profile tools stop pumba

test-chaos: ## Spin up the network, inject chaos, and verify resilience
	@echo "=> Starting Docker Compose for Chaos Smoke Test..."
	@PODMAN_COMPOSE_WARNING_LOGS=false docker compose -f docker/docker-compose.yml up -d --build --remove-orphans
	@echo "=> Running chaos smoke tests..."
	@PODMAN_COMPOSE_WARNING_LOGS=false docker compose -f docker/docker-compose.yml exec node-1 python tools/ci_chaos_smoke.py || (echo "=> Chaos test failed!"; PODMAN_COMPOSE_WARNING_LOGS=false docker compose -f docker/docker-compose.yml logs; PODMAN_COMPOSE_WARNING_LOGS=false docker compose -f docker/docker-compose.yml down; exit 1)
	@echo "=> Chaos test passed, tearing down network..."
	@PODMAN_COMPOSE_WARNING_LOGS=false docker compose -f docker/docker-compose.yml down

clean: ## Remove build artifacts, cache, and temporary files
	rm -rf dist/ build/ .eggs/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +

build: clean ## Build distribution packages (sdist and wheel)
	$(PYTHON) -m build

publish-testpypi: build ## Publish the library to TestPyPI
	$(PYTHON) -m twine upload --repository testpypi dist/*

publish-pypi: build ## Publish the library to PyPI (Production)
	$(PYTHON) -m twine upload dist/*

benchmark: ## Run the native performance benchmark and load test
	@echo "=> Starting native benchmark..."
	@if [ "$(NODES)" ]; then \
		$(PYTHON) tools/benchmark.py --nodes $(NODES); \
	else \
		$(PYTHON) tools/benchmark.py; \
	fi
