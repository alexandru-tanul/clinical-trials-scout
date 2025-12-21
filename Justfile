default:
    @just --list

# Download DrugCentral database dump
setup-drugcentral:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p data
    cd data
    [ -f "01-drugcentral.dump.11012023.sql.gz" ] || curl -L -o 01-drugcentral.dump.11012023.sql.gz https://unmtid-dbs.net/download/drugcentral.dump.11012023.sql.gz

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

# Access DrugCentral database
psql-drugcentral:
    docker compose exec drugcentral_db psql -U postgres -d drugcentral

# Update DrugCentral simplified views (run after modifying 02-create_simplified_views.sql)
update-drugcentral-views:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Checking if services are running..."
    if ! docker compose ps drugcentral_db | grep -q "Up"; then
        echo "Starting services..."
        docker compose up -d
        echo "Waiting for DrugCentral database to be ready..."
        sleep 10
    fi
    echo "Updating DrugCentral simplified views..."
    docker compose exec drugcentral_db psql -U postgres -d drugcentral -f /docker-entrypoint-initdb.d/02-create_simplified_views.sql
    echo "Views updated! Restarting FastAPI..."
    docker compose restart fastapi
    echo "✅ Done! The drug_targets view now includes gene columns for Pharos enrichment."

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