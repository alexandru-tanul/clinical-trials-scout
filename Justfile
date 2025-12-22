default:
    @just --list

# Initialize project: download dependencies and prepare environment
init:
    #!/usr/bin/env bash
    set -euo pipefail
    cp -n .env.example .env
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
    echo "========================================="
    echo "Project initialized successfully!"
    echo "========================================="
    echo ""
    echo "IMPORTANT: Before starting the services, please update the .env file with the correct values:"
    echo ""
    echo "  Required configuration:"
    echo "    - SECRET_KEY: Generate a secure random key"
    echo "    - ANTHROPIC_API_KEY: Your Anthropic API key"
    echo "    - OPENAI_API_KEY: Your OpenAI API key (if using OpenAI models)"
    echo "    - POSTGRES_PASSWORD: Secure password for PostgreSQL"
    echo "    - DRUGCENTRAL_PASSWORD: Secure password for DrugCentral database"
    echo ""
    echo "Once configured, start the services with:"
    echo "  just up"
    echo ""
    echo "Services will be available at:"
    echo "  - FastAPI: http://localhost:8000"
    echo "  - PgWeb:   http://localhost:8081"
    echo ""

# Build Docker images
build:
    docker compose build

# Start services
up:
    docker compose up

# Stop services
down:
    docker compose down
