#!/usr/bin/bash
set -euo pipefail

CMD="${1:-}"

case "$CMD" in
  app-up)
    SQL_DB_PATH=$(grep "^SQL_DB_PATH=" .env | cut -d= -f2)
    if [ ! -f "$SQL_DB_PATH/tasks.db" ]; then
      mkdir -p "$SQL_DB_PATH"
      touch "$SQL_DB_PATH/tasks.db"
      echo "Created SQLite database: $SQL_DB_PATH/tasks.db"
    fi
    docker compose -p semant-demo -f ./docker-compose.app.yaml up -d ;;
  app-down)
    docker compose -p semant-demo -f ./docker-compose.app.yaml down ;;
  app-build)
    docker compose -p semant-demo -f ./docker-compose.app.yaml build --no-cache;;

  database-up)
    docker compose -p semant-demo -f ./docker-compose.database.yml up -d ;;
  database-down)
    docker compose -p semant-demo -f ./docker-compose.database.yml down ;;

  test-database-up)
    docker compose -p semant-demo -f ./docker-compose.database-test.yml up -d ;;
  test-database-down)
    docker compose -p semant-demo -f ./docker-compose.database-test.yml down ;;

  embedder-up)
    docker compose -p semant-demo -f ./docker-compose.embedder.yml up -d ;;
  embedder-down)
    docker compose -p semant-demo -f ./docker-compose.embedder.yml down ;;
  embedder-build)
    docker compose -p semant-demo -f ./docker-compose.embedder.yml build --no-cache;;

  *)
    echo "Usage: $0 <command>"
    echo ""
    echo "  app-up / app-down / app-build          production app"
    echo "  database-up / database-down    production weaviate"
    echo "  test-database-up / test-database-down  test weaviate"
    echo "  embedder-up / embedder-down / embedder-build  embedder"
    exit 1 ;;
esac
