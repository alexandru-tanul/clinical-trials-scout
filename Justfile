default:
    @just --list

run *args:
    #!/usr/bin/env sh
    # Start the FastAPI server via Docker
    docker compose up -d

    # Open the browser (after 2s)
    sleep 2 && py -m webbrowser http://127.0.0.1:8000/

# ====================================
# Docker Commands
# ====================================
# Set COMPOSE_FILE env var to choose config:
#   export COMPOSE_FILE=docker-compose.local.yml      (default)
#   export COMPOSE_FILE=docker-compose.production.yml

# Build Docker images
build:
    docker compose build

# Start services
up:
    docker compose up

# Stop services
down:
    docker compose down

# View logs
logs:
    docker compose logs -f

# Access PostgreSQL database
psql:
    docker compose exec postgres psql -U postgres -d chatbot

# Run Aerich migrations (upgrade database)
migrate:
    docker compose run --rm fastapi aerich upgrade

# Create Aerich migrations
makemigrations:
    docker compose run --rm fastapi aerich migrate

# Initialize Aerich (run once for new projects)
init-db:
    docker compose run --rm fastapi aerich init-db

# Access Python shell (Docker)
shell:
    docker compose run --rm fastapi python -i -c "from tortoise import Tortoise; import asyncio; asyncio.run(Tortoise.init(config_file='aerich.ini'))"

# Rebuild Tailwind CSS manually
css:
    docker compose restart tailwindcss