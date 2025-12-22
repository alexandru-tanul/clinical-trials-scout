default:
    @just --list

# Initialize project: download dependencies and setup databases
init:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Downloading DrugCentral database dump..."
    mkdir -p data
    cd data
    if [ ! -f "01-drugcentral.dump.11012023.sql.gz" ]; then
        curl -L -o 01-drugcentral.dump.11012023.sql.gz \
            https://unmtid-dbs.net/download/drugcentral.dump.11012023.sql.gz
        echo "DrugCentral database dump downloaded"
    else
        echo "DrugCentral database dump already exists"
    fi
    cd ..
    echo ""
    echo "Building Docker images..."
    docker compose build
    echo ""
    echo "Starting services and initializing databases..."
    docker compose up -d
    echo ""
    echo "Waiting for databases to initialize (this may take a few minutes on first run)..."
    echo "You can monitor progress with: docker compose logs -f"
    echo ""
    echo "Project initialized! Services are running:"
    echo "  - FastAPI: http://localhost:8000"
    echo "  - PgWeb:   http://localhost:8081"

# Build Docker images
build:
    docker compose build

# Start services
up:
    docker compose up

# Stop services
down:
    docker compose down
