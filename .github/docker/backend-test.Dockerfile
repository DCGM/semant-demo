FROM python:3.12-slim

# git je potreba pro dorny/test-reporter (napr. vypis souboru sledovanych gitem)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates && \
    rm -rf /var/lib/apt/lists/*
