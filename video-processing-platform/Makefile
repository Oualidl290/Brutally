# Video Processing Platform Makefile

.PHONY: help install install-dev test test-cov lint format clean dev docker-build docker-run setup-dev

# Default target
help:
	@echo "Video Processing Platform - Available Commands:"
	@echo ""
	@echo "Development:"
	@echo "  setup-dev     - Set up development environment"
	@echo "  install       - Install production dependencies"
	@echo "  install-dev   - Install development dependencies"
	@echo "  dev           - Start development server"
	@echo ""
	@echo "Testing:"
	@echo "  test          - Run tests"
	@echo "  test-cov      - Run tests with coverage"
	@echo "  test-e2e      - Run end-to-end tests"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint          - Run linting"
	@echo "  format        - Format code"
	@echo "  type-check    - Run type checking"
	@echo ""
	@echo "Docker:"
	@echo "  docker-build  - Build Docker images"
	@echo "  docker-run    - Run with docker-compose"
	@echo "  docker-dev    - Run development environment"
	@echo ""
	@echo "Utilities:"
	@echo "  clean         - Clean temporary files"
	@echo "  init          - Initialize project directories"

# Development setup
setup-dev: install-dev init
	@echo "✅ Development environment ready!"
	@echo "Next steps:"
	@echo "  1. Copy .env.example to .env and configure"
	@echo "  2. Run 'make docker-dev' to start services"
	@echo "  3. Run 'make dev' to start development server"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

# Testing
test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=src --cov-report=html --cov-report=term

test-e2e:
	pytest tests/test_e2e_cli.py -v

test-api:
	python scripts/test_api_endpoints.py

test-api-output:
	python scripts/test_api_endpoints.py --output api_test_results.json

check-frontend-ready:
	python scripts/check_frontend_readiness.py

check-frontend-ready-output:
	python scripts/check_frontend_readiness.py --output frontend_readiness.json

# Code quality
lint:
	flake8 src tests
	pylint src

format:
	black src tests
	isort src tests

type-check:
	mypy src

# Development server
dev:
	video-processor server start --reload --host 0.0.0.0

# Docker
docker-build:
	docker build -t video-processing-platform .

docker-run:
	docker-compose up -d

docker-dev:
	docker-compose -f docker-compose.dev.yml up -d

docker-stop:
	docker-compose down

docker-logs:
	docker-compose logs -f

# Utilities
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	rm -rf build/
	rm -rf dist/
	rm -rf htmlcov/
	rm -rf .coverage

init:
	mkdir -p output temp cache logs
	video-processor init

# CLI shortcuts
server-start:
	video-processor server start

worker-start:
	video-processor worker start

health-check:
	video-processor health check

jobs-list:
	video-processor jobs list

# Production deployment
deploy-prod:
	docker-compose -f docker-compose.yml up -d --build

deploy-staging:
	docker-compose -f docker-compose.yml up -d --build
	docker-compose exec api video-processor config validate

# Database management
db-migrate:
	alembic upgrade head

db-reset:
	alembic downgrade base
	alembic upgrade head

# Monitoring
monitor:
	video-processor worker monitor

logs:
	tail -f logs/*.log

# Release
release-patch:
	bump2version patch

release-minor:
	bump2version minor

release-major:
	bump2version major