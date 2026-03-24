#!/usr/bin/bash

# Load environment variables from .env
. .env

export now=$(date +"%Y-%m-%d %H:%M:%S")

docker compose -f ./docker-compose.yaml "$@"
