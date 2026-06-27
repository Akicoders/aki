# Makefile for AgentOS

.PHONY: help install dev test lint format typecheck build run clean docker-build docker-run docker-prod

# Default target
help:
	@echo "AgentOS - Personal AI agent with persistent memory"
	@echo ""
	@echo "Usage:"
	@echo "  make install       Install dependencies with uv"
	@echo "  make dev           Run in development mode"
	@echo "  make test          Run tests"
	@echo "  make lint          Run ruff linter"
	@echo "  make format        Format code with ruff"
	@echo "  make typecheck     Run mypy type checker"
	@echo "  make build         Build Docker image"
	@echo "  make run           Run with docker-compose"
	@echo "  make prod          Run production docker-compose"
	@echo "  make clean         Clean build artifacts"

# Install dependencies
install:
	uv sync --all-extras

# Development
dev:
	uv run agentos interactive

# Run with specific project
dev-project:
	uv run agentos interactive --project $(PROJECT)

# Test
test:
	uv run pytest -v

test-cov:
	uv run pytest -v --cov=src/agentos --cov-report=html

test-unit:
	uv run pytest -v -m unit

test-integration:
	uv run pytest -v -m integration

# Lint
lint:
	uv run ruff check .

lint-fix:
	uv run ruff check --fix .

# Format
format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

# Typecheck
typecheck:
	uv run mypy src/

# Pre-commit
pre-commit:
	uv run pre-commit run --all-files

pre-commit-install:
	uv run pre-commit install

# Docker
docker-build:
	docker build -t agentos-memory:latest .

docker-build-prod:
	docker build -t agentos-memory:latest --target production .

docker-run:
	docker compose up -d

docker-logs:
	docker compose logs -f

docker-stop:
	docker compose down

docker-prod:
	docker compose -f docker-compose.prod.yml up -d

docker-prod-logs:
	docker compose -f docker-compose.prod.yml logs -f

docker-prod-stop:
	docker compose -f docker-compose.prod.yml down

# Clean
clean:
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .mypy_cache/ .ruff_cache/ htmlcov/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

clean-data:
	rm -rf data/ chroma_db/ *.db

# Database
db-init:
	uv run python -c "from agentos.memory.database import get_database; get_database(); print('DB initialized')"

db-migrate:
	uv run alembic upgrade head

db-revision:
	uv run alembic revision --autogenerate -m "$(MSG)"

# Memory
memory-stats:
	uv run python -c "
from agentos.memory.repository import MemoryRepository
repo = MemoryRepository()
import asyncio
async def stats():
    from agentos.memory.models import EventType
    events = repo.search_events('', limit=1000)
    facts = repo.get_facts_by_scope('project:default')
    print(f'Events: {len(events)}')
    print(f'Facts: {len(facts)}')
asyncio.run(stats())
"

# Skills test
test-skills:
	uv run python -c "
import asyncio
from agentos.skills import BUILTIN_SKILLS
from agentos.skills.base import get_skill_registry

async def test():
    registry = get_skill_registry()
    for name, cls in BUILTIN_SKILLS.items():
        skill = cls()
        registry.register(skill)
        print(f'✓ {name}: {skill.functions}')
    tools = registry.get_all_tools()
    print(f'Total tools: {len(tools)}')

asyncio.run(test())
"

# Quick chat test
chat-test:
	uv run agentos chat "hola, recordá que en ERP-AI usamos pnpm" --project ERP-AI

chat-recall:
	uv run agentos recall "package manager" --project ERP-AI

# Version
version:
	@uv run python -c "import agentos; print(agentos.__version__)"

# Install git hooks
hooks:
	uv run pre-commit install
	uv run pre-commit install --hook-type commit-msg