#!/usr/bin/env bash
# Build the browser CI image and push it to the local CI registry (#715).
# Prints the digest reference to put in .github/workflows/ci-cd.yml (test-browser-shard).
set -euo pipefail
cd "$(dirname "$0")/../.."

REGISTRY=${REGISTRY:-localhost:5000}
PLAYWRIGHT_VERSION=$(node -p "require('./semant_demo_frontend/package-lock.json').packages['node_modules/@playwright/test'].version")
IMAGE="$REGISTRY/semant-ci-browser:playwright-$PLAYWRIGHT_VERSION"

# Base on the python:3.12 the other CI jobs currently get.
docker pull python:3.12
PYTHON_IMAGE=$(docker image inspect python:3.12 --format '{{index .RepoDigests 0}}')
NODE_IMAGE=$(grep -o 'node:[0-9.]*-bookworm@sha256:[0-9a-f]*' .github/workflows/ci-cd.yml | head -n1)

docker build -f deploy/ci/Dockerfile.browser \
  --build-arg PYTHON_IMAGE="$PYTHON_IMAGE" \
  --build-arg NODE_IMAGE="$NODE_IMAGE" \
  --build-arg PLAYWRIGHT_VERSION="$PLAYWRIGHT_VERSION" \
  -t "$IMAGE" deploy/ci
docker push "$IMAGE"
echo "Pinned reference: $(docker image inspect "$IMAGE" --format '{{index .RepoDigests 0}}')"
