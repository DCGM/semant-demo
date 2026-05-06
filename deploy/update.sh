#!/usr/bin/bash
set -euo pipefail

CMD="${1:-}"

case "$CMD" in
  app-up)
    docker compose -p semant-demo -f ./docker-compose.app.yaml up -d ;;
  app-down)
    docker compose -p semant-demo -f ./docker-compose.app.yaml down ;;
  app-build)
    docker compose -p semant-demo -f ./docker-compose.app.yaml build ;;

  database-up)
    docker compose -p semant-demo -f ./docker-compose.database.yml up -d ;;
  database-down)
    docker compose -p semant-demo -f ./docker-compose.database.yml down ;;

  test-database-up)
    docker compose -p semant-demo-test -f ./docker-compose.database-test.yml up -d ;;
  test-database-down)
    docker compose -p semant-demo-test -f ./docker-compose.database-test.yml down ;;

  embedder-up)
    docker compose -p semant-demo -f ./docker-compose.embedder.yml up -d ;;
  embedder-down)
    docker compose -p semant-demo -f ./docker-compose.embedder.yml down ;;
  embedder-build)
    docker compose -p semant-demo -f ./docker-compose.embedder.yml build ;;

  topicer-up)
    docker compose -p semant-demo -f ./docker-compose.topicer.yml up -d ;;
  topicer-down)
    docker compose -p semant-demo -f ./docker-compose.topicer.yml down ;;
  topicer-build)
    docker compose -p semant-demo -f ./docker-compose.topicer.yml build ;;
  
  test-topicer-up)
    docker compose -p semant-demo -f ./docker-compose.topicer-test.yml up -d ;;
  test-topicer-down)
    docker compose -p semant-demo -f ./docker-compose.topicer-test.yml down ;;
  test-topicer-build)
    docker compose -p semant-demo -f ./docker-compose.topicer-test.yml build ;;
  *)
    echo "Usage: $0 <command>"
    echo ""
    echo "  app-up / app-down / app-build          production app"
    echo "  database-up / database-down    production weaviate"
    echo "  test-database-up / test-database-down  test weaviate"
    echo "  embedder-up / embedder-down / embedder-build  embedder"
    echo "  topicer-up / topicer-down / topicer-build  topicer"
    echo "  test-topicer-up / test-topicer-down / test-topicer-build  topicer test instance"
    exit 1 ;;
esac
