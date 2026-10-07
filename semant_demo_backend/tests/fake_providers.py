"""Deterministic HTTP stand-ins for the embedding service and Topicer.

Used by the browser-test profile (``tests/e2e_server.py``), where the backend reaches its
providers over HTTP. Every other provider route answers 501, so a feature that would call
an unfaked provider (OpenAI-compatible chat, Ollama, Gemini) fails visibly instead of
reaching a real service.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from tests.corpus import Corpus
from tests.fakes import fake_embedding

FAKE_REASON = "fake provider: tag example found in text"


def propose_spans(text: str, tags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One proposal per occurrence of a tag example in ``text`` (Python str offsets)."""
    proposals = []
    for tag in tags:
        for example in tag.get("examples") or []:
            start = text.find(example) if example else -1
            while start >= 0:
                proposals.append({
                    "tag": {"id": tag["id"], "name": tag.get("name", "")},
                    "span_start": start,
                    "span_end": start + len(example),
                    "reason": FAKE_REASON,
                    "confidence": 1.0,
                })
                start = text.find(example, start + 1)
    return proposals


def create_fake_provider_app(corpus: Corpus) -> FastAPI:
    app = FastAPI(title="Fake AI providers")

    @app.post("/embed_query")
    async def embed_query(body: dict):
        return {"embedding": fake_embedding(body["query"])}

    @app.post("/embed_documents")
    async def embed_documents(body: dict):
        return {"embeddings": [fake_embedding(t) for t in body["texts"]]}

    @app.post("/v1/tags/propose/texts")
    async def propose_texts(body: dict):
        chunk = body["text_chunk"]
        return {"text_chunk": chunk, "tag_span_proposals": propose_spans(chunk["text"], body["tags"])}

    @app.post("/v1/tags/propose/db/stream")
    async def propose_db_stream(body: dict):
        # The real Topicer reads chunks from the database; the fake reads the corpus.
        request = body["db_request"]
        collection_key = next(
            (k for k, c in corpus.collections.items() if c["id"] == request["collection_id"]), None)
        chunks = sorted(
            (c for c in corpus.chunks.values()
             if corpus.documents[c["document"]]["id"] == request["document_id"]
             and collection_key in c["collections"]),
            key=lambda c: c["order"],
        )

        async def lines():
            for chunk in chunks:
                event = {"id": chunk["id"], "text": chunk["text"],
                         "tag_span_proposals": propose_spans(chunk["text"], [body["tag"]])}
                yield json.dumps(event, ensure_ascii=False) + "\n"

        return StreamingResponse(lines(), media_type="application/x-ndjson")

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def not_faked(path: str, request: Request):
        return JSONResponse(
            status_code=501,
            content={"detail": f"{request.method} /{path} is not provided by the fake AI providers."},
        )

    return app
