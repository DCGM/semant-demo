"""Deterministic HTTP stand-ins for the embedding service, an OpenAI-compatible embedding
endpoint (``/openai/v1/embeddings``: the second search vector), Topicer and LLM chat
(Ollama ``/ollama/api/chat`` and OpenAI-compatible ``/openai/v1/chat/completions``).

Used by the browser-test profile (``tests/e2e_server.py``), where the backend reaches its
providers over HTTP, and as the ``llm_transport`` of the LLM gateway in tests. Every other
provider route answers 501, so a feature that would call an unfaked provider fails
visibly instead of reaching a real service.

Chat replies report token usage (whitespace-separated words) unless the requested model
name contains ``no-usage``. OpenAI-compatible replies also report an OpenRouter-style
``usage.cost`` (``FAKE_COST_PER_TOKEN`` per token) when the model name contains
``reported-cost``, also in the final usage chunk of a stream, and an invalid negative one when
it contains ``negative-cost``. With tools offered, the OpenAI fake acts as a minimal agent:
it searches for the question, then synthesizes the found passages, then answers.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from tests.corpus import Corpus
from tests.fakes import SECOND_VECTOR, fake_embedding, second_embedding

FAKE_REASON = "fake provider: tag example found in text"
FAKE_COST_PER_TOKEN = 3e-6
# Read without importing semant_demo, whose settings must see the profile's environment.
DEFAULT_LLM_MODELS_CONFIG = Path(__file__).parents[1] / "semant_demo" / "configs" / "llm_models.yaml"
# The annotation vector embedded by the fake embedding service; its `id` is the one stored in
# existing local development data.
FAKE_ANNOTATION_VECTOR_CONFIG = Path(__file__).parents[1] / "semant_demo" / "configs" / "annotation_vector_gemma.yaml"


def fake_provider_environ(config_dir: Path, fake_url: str, fake_port: int) -> dict[str, str]:
    """Application settings that point every AI provider at the fakes served on
    ``fake_url`` (port ``fake_port``), with no API keys, so no live or paid provider can be
    reached (tiers on keyed providers are refused before any request). Writes the model tier
    catalog and the search vectors they use into ``config_dir``; the annotation vector
    uses the fake embedding service. Used by the browser-test
    profile (``tests/e2e_server.py``) and the local development profile (``tests/local_dev.py``)."""
    # The default model tiers without per-tier endpoints: every tier uses the fake provider.
    catalog = yaml.safe_load(DEFAULT_LLM_MODELS_CONFIG.read_text())
    for tier in catalog["tiers"].values():
        tier.pop("base_url", None)
    llm_models_path = config_dir / "llm_models.yaml"
    llm_models_path.write_text(yaml.safe_dump(catalog))
    # Both named chunk vectors of the fixture store (#217), embedded by the fake providers.
    search_vectors_path = config_dir / "search_vectors.yaml"
    search_vectors_path.write_text(yaml.safe_dump({"default": "fake-default", "vectors": [
        {"id": "fake-default", "name": "Fake default", "description": "The test store's default vector.",
         "target_vector": "default", "embedding": {"provider": "embedding_service"}},
        {"id": "fake-small", "name": "Fake small", "description": "The test store's second vector.",
         "target_vector": SECOND_VECTOR, "embedding": {"provider": "openai", "base_url": f"{fake_url}/openai/v1",
                                                 "model": "fake-small"}},
    ]}))
    return {
        "LLM_MODELS_CONFIG": str(llm_models_path),
        "SEARCH_VECTORS_CONFIG": str(search_vectors_path),
        "ANNOTATION_VECTOR_CONFIG": str(FAKE_ANNOTATION_VECTOR_CONFIG),
        "EMBEDDING_SERVICE_HOST": "127.0.0.1",
        "EMBEDDING_SERVICE_PORT": str(fake_port),
        "TOPICER_URL": fake_url,
        "OPENAI_API_URL": f"{fake_url}/openai/v1",
        "OLLAMA_URLS": f"{fake_url}/ollama",
        "OPENAI_API_KEY": "e2e-fake-openrouter-key",
        "GOOGLE_API_KEY": "",
    }


def fake_chat_answer(messages: list[dict[str, Any]]) -> str:
    """Names how many ``[docN]`` passages the last user message holds and cites the last
    one, so a test can tell which subset of results was sent (citations are numbered per
    prompt). The system prompt is ignored: it shows example labels."""
    user_messages = [m for m in messages if m.get("role") == "user"]
    prompt = str(user_messages[-1].get("content", "")) if user_messages else ""
    labels = sorted({int(n) for n in re.findall(r"\[doc ?([1-9][0-9]*)]", prompt)})
    if not labels:
        return "Fake summary without passages."
    return f"Fake summary of {len(labels)} passage(s); last [doc{labels[-1]}]."


def _pieces(text: str) -> list[str]:
    """``text`` split into streamed deltas that join back to it."""
    words = text.split(" ")
    return [words[0]] + [" " + w for w in words[1:]]


def _words(messages: list[dict[str, Any]]) -> int:
    return sum(len(str(m.get("content") or "").split()) for m in messages)


def _reports_usage(body: dict) -> bool:
    return "no-usage" not in str(body.get("model", ""))


def _reports_cost(body: dict) -> bool:
    return "reported-cost" in str(body.get("model", ""))


def fake_agent_step(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The tool call the fake agent makes next, or ``None`` when it answers."""
    called = [c["function"]["name"] for m in messages if m.get("role") == "assistant"
              for c in m.get("tool_calls") or []]
    question = next(str(m.get("content")) for m in messages if m.get("role") == "user")
    if "weaviate_search" not in called:
        return {"name": "weaviate_search", "arguments": {"query": question}}
    if "synthesize_evidence" not in called:
        found = next(str(m.get("content")) for m in reversed(messages) if m.get("role") == "tool")
        return {"name": "synthesize_evidence", "arguments": {"question": question, "retrieved_documents": found}}
    return None


def openai_chat_reply(body: dict) -> dict[str, Any]:
    """The assistant ``message`` an OpenAI-compatible endpoint returns for ``body``."""
    messages = body.get("messages", [])
    step = fake_agent_step(messages) if body.get("tools") else None
    if step is not None:
        call_id = f"call_{len(messages)}"
        return {"role": "assistant", "content": None, "tool_calls": [{
            "id": call_id, "type": "function",
            "function": {"name": step["name"], "arguments": json.dumps(step["arguments"], ensure_ascii=False)}}]}
    if body.get("tools"):
        synthesized = next(str(m.get("content")) for m in reversed(messages) if m.get("role") == "tool")
        return {"role": "assistant", "content": synthesized}
    return {"role": "assistant", "content": fake_chat_answer(messages)}


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


FAKE_TOPICER_CALL_COST_USD = 0.0001
"""Reported cost of each fake Topicer model call."""
FAKE_TOPICER_MAX_CHUNKS_CEILING = 200


def fake_topicer_usage(calls: int) -> dict[str, Any]:
    """Topicer's ``LLMUsage`` (DCGM/topicer#81) of ``calls`` successful, priced calls."""
    call = {"provider": "fake", "model": "fake-topicer", "outcome": "success", "input_tokens": 100,
            "output_tokens": 10, "usage_source": "reported", "cost_usd": FAKE_TOPICER_CALL_COST_USD,
            "cost_source": "reported"}
    return {"attempted_calls": calls, "completed_calls": calls, "failed_calls": 0, "calls": [call] * calls}


def create_fake_provider_app(corpus: Corpus, stream_delay: float = 0.0) -> FastAPI:
    """``stream_delay``: seconds the Topicer stream waits after each chunk event, so a
    browser test can act (cancel, navigate) while a suggestion run is still under way."""
    app = FastAPI(title="Fake AI providers")

    @app.post("/embed_query")
    async def embed_query(body: dict):
        return {"embedding": fake_embedding(body["query"])}

    @app.post("/embed_documents")
    async def embed_documents(body: dict):
        return {"embeddings": [fake_embedding(t) for t in body["texts"]]}

    # OpenAI-compatible embeddings (a search vector's query model, #217): the second vector.
    @app.post("/openai/v1/embeddings")
    async def openai_embeddings(body: dict):
        return {"object": "list", "model": body["model"],
                "data": [{"object": "embedding", "index": i, "embedding": second_embedding(t)}
                         for i, t in enumerate(body["input"])]}

    @app.post("/v1/tags/propose/texts")
    async def propose_texts(body: dict):
        chunk = body["text_chunk"]
        return {"text_chunk": chunk, "tag_span_proposals": propose_spans(chunk["text"], body["tags"]),
                "usage": fake_topicer_usage(1)}

    @app.post("/v1/tags/propose/db/stream")
    async def propose_db_stream(body: dict, max_chunks: int | None = None):
        if max_chunks is not None and not 0 < max_chunks <= FAKE_TOPICER_MAX_CHUNKS_CEILING:
            raise HTTPException(422, "max_chunks out of range")
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

        # As Topicer: at most max_chunks chunks, then the terminal usage summary.
        limit = max_chunks if max_chunks is not None else len(chunks)
        processed = chunks[:limit]

        async def lines():
            for index, chunk in enumerate(processed):
                if index and stream_delay:
                    await asyncio.sleep(stream_delay)
                event = {"id": chunk["id"], "text": chunk["text"],
                         "tag_span_proposals": propose_spans(chunk["text"], [body["tag"]])}
                yield json.dumps(event, ensure_ascii=False) + "\n"
            summary = {"event": "usage_summary", "status": "complete", "tag_id": body["tag"]["id"],
                       "max_chunks": max_chunks, "max_chunks_source": "request" if max_chunks is not None else None,
                       "processed_chunks": len(processed),
                       "limit_reached": max_chunks is not None and len(processed) >= max_chunks,
                       "candidates_truncated": len(chunks) > limit, "usage": fake_topicer_usage(len(processed))}
            yield json.dumps(summary) + "\n"

        return StreamingResponse(lines(), media_type="application/x-ndjson")

    @app.post("/ollama/api/chat")
    async def ollama_chat(body: dict):
        answer = fake_chat_answer(body.get("messages", []))
        usage = ({"prompt_eval_count": _words(body.get("messages", [])), "eval_count": len(answer.split())}
                 if _reports_usage(body) else {})
        last = {"model": body.get("model", ""), "created_at": "2026-01-01T00:00:00Z", "done": True,
                "done_reason": "stop", "message": {"role": "assistant", "content": ""}, **usage}
        if not body.get("stream", True):
            return {**last, "message": {"role": "assistant", "content": answer}}

        async def lines():
            for piece in _pieces(answer):
                yield json.dumps({"model": body.get("model", ""), "created_at": "2026-01-01T00:00:00Z",
                                  "done": False, "message": {"role": "assistant", "content": piece}}) + "\n"
            yield json.dumps(last) + "\n"

        return StreamingResponse(lines(), media_type="application/x-ndjson")

    @app.post("/openai/v1/chat/completions")
    async def openai_chat(body: dict):
        message = openai_chat_reply(body)
        usage = {"prompt_tokens": _words(body.get("messages", [])),
                 "completion_tokens": len(str(message.get("content") or "").split())}
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
        if _reports_cost(body):
            usage["cost"] = usage["total_tokens"] * FAKE_COST_PER_TOKEN
        elif "negative-cost" in str(body.get("model", "")):
            usage["cost"] = -1.0
        base = {"id": "fake", "created": 1767225600, "model": body.get("model", "")}
        if not body.get("stream"):
            return {**base, "object": "chat.completion",
                    "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
                    **({"usage": usage} if _reports_usage(body) else {})}

        def chunk(**fields) -> str:
            return "data: " + json.dumps({**base, "object": "chat.completion.chunk", **fields}) + "\n\n"

        async def events():
            for piece in _pieces(str(message.get("content") or "")):
                yield chunk(choices=[{"index": 0, "delta": {"content": piece}, "finish_reason": None}])
            yield chunk(choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}])
            if _reports_usage(body) and (body.get("stream_options") or {}).get("include_usage"):
                yield chunk(choices=[], usage=usage)
            yield "data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def not_faked(path: str, request: Request):
        return JSONResponse(
            status_code=501,
            content={"detail": f"{request.method} /{path} is not provided by the fake AI providers."},
        )

    return app
