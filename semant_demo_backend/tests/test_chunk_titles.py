"""Chunk title generation (#575): prompt, reply validation, planning, selection files, model
calls through the real gateway against fake providers, provenance and exit codes. The runs
against a store are in ``tests/integration/test_chunk_titles.py``."""
import asyncio
import json
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from httpx import ASGITransport

from semant_demo.adapters.llm.gateway import LlmGateway, ProviderSettings
from semant_demo.adapters.llm.models import ModelCatalog
from semant_demo.adapters.weaviate.chunk_titles import ChunkState
from semant_demo.maintenance import chunk_titles
from semant_demo.maintenance.chunk_titles import (
    FEATURE, InvalidTitle, Refused, Selection, UsageTotals, clean_title, exit_code, generate_title, language_key,
    messages, plan, provenance, read_id_file,
)
from tests.corpus import load_corpus
from tests.fake_providers import create_fake_provider_app

DOC, OTHER, CHUNK = (UUID(f"7171e000-0000-4000-8000-00000000000{n}") for n in range(1, 4))


def catalog(provider="ollama", **limits) -> dict:
    return {"tiers": {"tiny": {"provider": provider, "model": "fake-titles", "price_basis": "local_rate",
                               "input_price": 0, "output_price": 0}},
            "features": {FEATURE: {"default": "tiny", "limits": {"max_output_tokens": 64, **limits}}}}


def gateway(transport, data=None, usage=None, **providers) -> LlmGateway:
    settings = {"openai_base_url": "http://fake/openai/v1", "ollama_base_url": "http://fake/ollama",
                "max_retries": 0, **providers}
    return LlmGateway(ModelCatalog.from_dict(data or catalog()), ProviderSettings(**settings), usage,
                      http_transport=transport)


def fake_transport():
    return ASGITransport(app=create_fake_provider_app(load_corpus()))


class ReplyTransport(httpx.AsyncBaseTransport):
    """An Ollama chat endpoint answering every request with ``replies`` in turn (an int is an HTTP error)."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = 0

    async def handle_async_request(self, request):
        self.requests += 1
        reply = self.replies[min(self.requests, len(self.replies)) - 1]
        if isinstance(reply, int):
            return httpx.Response(reply, json={"error": "secret prompt text"})
        return httpx.Response(200, json={"model": "fake-titles", "created_at": "2026-11-03T00:00:00Z", "done": True,
                                         "done_reason": "stop", "message": {"role": "assistant", "content": reply},
                                         "prompt_eval_count": 10, "eval_count": 3})


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(chunk_titles, "BACKOFF", 0)


@pytest.mark.parametrize("reply, title", [
    ("Příjezd hejtmana do Lhoty", "Příjezd hejtmana do Lhoty"),
    ("  „Příjezd hejtmana“ \n", "Příjezd hejtmana"),
    ('"**Příjezd   hejtmana**"', "Příjezd hejtmana"),
    ("## Příjezd hejtmana", "Příjezd hejtmana"),
    ("Požár: zkáza obce", "Požár: zkáza obce"),
    # quotes inside the title are not a pair around it
    ("„Svatý Václav“ a „Karel IV.“", "„Svatý Václav“ a „Karel IV.“"),
    ('"Foo" and "Bar"', '"Foo" and "Bar"'),
    ("«Kronika»", "Kronika"),
    # emphasis inside the title is not a pair around it
    ("**Požár** v obci **Brno**", "**Požár** v obci **Brno**"),
    ("_a_ and _b_", "_a_ and _b_"),
    ("*Kronika*", "Kronika"),
])
def test_clean_title_keeps_only_the_title(reply, title):
    assert clean_title(reply) == title


async def test_a_failing_call_cancels_the_others_before_the_error_propagates():
    started, cancelled = [], []

    async def call(item):
        started.append(item)
        if item == 0:
            await asyncio.sleep(0)
            raise Refused("refused")
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.append(item)
            raise
    with pytest.raises(Refused):
        await chunk_titles._gather(range(4), 4, call)
    assert started == [0, 1, 2, 3] and sorted(cancelled) == [1, 2, 3]


@pytest.mark.parametrize("reply", [
    "", "  \n ", '""',
    "Title: one\nTitle: two", " ".join(["slovo"] * 21), "x" * 201,
])
def test_clean_title_refuses_what_is_not_a_title(reply):
    with pytest.raises(InvalidTitle):
        clean_title(reply)


@pytest.mark.parametrize("value, key", [
    ("ces", "ces"), (" deu ", "deu"), (["ces"], "ces"), (["ces", "ces"], "ces"), (["ces", "deu"], "(mixed)"),
    (None, "(unknown)"), ("", "(unknown)"), ([], "(unknown)"), (3, "(unknown)"),
])
def test_language_key(value, key):
    assert language_key(value) == key


def test_messages_end_with_the_named_language_and_leave_out_a_missing_document_title():
    full = messages("Požár zničil obec.", "ces", "Kronika obce Lhota")
    assert full[0]["role"] == "system" and "not a sentence" in full[0]["content"]
    assert full[1]["content"] == ("Original Document Title:\nKronika obce Lhota\n\n"
                                  "Excerpt Text:\nPožár zničil obec.\n\nWrite the heading in Czech.")
    assert messages("Brand in Wien.", "deu", None)[1]["content"] == (
        "Excerpt Text:\nBrand in Wien.\n\nWrite the heading in German.")


@pytest.mark.parametrize("language", [None, "yue", "xyz"])
def test_an_unknown_or_missing_language_is_not_named(language):
    # A wrong code (yue on a Czech text) must not ask for a heading in that language.
    assert messages("Text {with} braces", language, None)[1]["content"] == (
        "Excerpt Text:\nText {with} braces\n\nWrite the heading in the language of the excerpt.")


def chunk(title=None, *documents, language=None) -> ChunkState:
    return ChunkState(CHUNK, title, language, tuple(documents))


def test_plan_skips_titled_chunks_and_defers_documents_without_a_title():
    titles = {DOC: "Kronika", OTHER: "  "}
    assert plan(chunk("Požár", DOC), titles) == ("has_title", None)
    assert plan(chunk("Požár", DOC), titles, regenerate=True) == ("generate", "Kronika")
    assert plan(chunk("  ", DOC), titles) == ("generate", "Kronika")   # a blank title is no title
    assert plan(chunk(None, OTHER), titles) == ("deferred_no_document_title", None)
    assert plan(chunk(None, OTHER), titles, allow_missing_document_title=True) == ("generate", None)
    assert plan(chunk(None), titles) == ("no_document", None)
    assert plan(chunk(None, UUID(int=9)), titles) == ("missing_document", None)
    assert plan(chunk(None, DOC, OTHER), titles) == ("several_documents", None)


def test_selection_identity_ignores_order_and_duplicates():
    assert Selection().identity() == {"kind": "untitled"}
    one = Selection(True, (DOC, OTHER), (CHUNK,)).identity()
    assert one == Selection(True, (OTHER, DOC, DOC), (CHUNK,)).identity()
    assert one["documents"] == 2 and one["chunks"] == 1
    assert one != Selection(True, (DOC,), (CHUNK,)).identity()
    assert Selection(True).identity()["kind"] == "explicit"   # an empty file selects nothing, not everything


def test_id_files(tmp_path):
    text = tmp_path / "documents.txt"
    text.write_text(f"# new documents\n{DOC}\n\n{OTHER}  # second\n")
    assert read_id_file(text) == [DOC, OTHER]
    text.write_text("not-a-uuid\n")
    with pytest.raises(Refused, match="documents.txt:1"):
        read_id_file(text)


async def test_generate_title_through_the_gateway():
    usage = UsageTotals()
    llm = gateway(fake_transport(), usage=usage)
    status, title = await generate_title(llm, messages("Požár v roce 1850 zničil polovinu obce.", "ces", "Kronika"))
    assert (status, title) == ("generated", "Požár v roce 1850")
    assert usage.totals["calls"] == 1 and usage.totals["cost_usd"] == 0 and usage.totals["unknown_cost_calls"] == 0


async def test_a_thinking_model_separated_by_ollama_gives_just_the_title():
    data = catalog()
    data["tiers"]["tiny"]["thinking"] = "separate"   # the fake then reasons over several lines first
    status, title = await generate_title(gateway(fake_transport(), data),
                                         messages("Požár v roce 1850 zničil polovinu obce.", "ces", "Kronika"))
    assert (status, title) == ("generated", "Požár v roce 1850")


async def test_ollama_gets_a_context_for_the_whole_input():
    transport = ReplyTransport("Titulek")
    seen = []

    class Recording(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            seen.append(json.loads(request.content))
            return await transport.handle_async_request(request)
    assert await generate_title(gateway(Recording()), messages("Text.", None, None), context_size=4608) == (
        "generated", "Titulek")
    assert seen[0]["options"]["num_ctx"] == 4608 and seen[0]["options"]["num_predict"] == 64


async def test_an_invalid_reply_is_tried_again_and_then_reported():
    transport = ReplyTransport("first line\nsecond line", "Titulek")
    assert await generate_title(gateway(transport), messages("Text.", None, None)) == ("generated", "Titulek")
    transport = ReplyTransport("")
    assert await generate_title(gateway(transport), messages("Text.", None, None)) == ("invalid_output", "empty")
    assert transport.requests == chunk_titles.ATTEMPTS


async def test_a_failing_model_is_reported_by_exception_class_only():
    transport = ReplyTransport(500)
    status, reason = await generate_title(gateway(transport), messages("Text.", None, None))
    assert status == "model_failed" and "secret" not in reason and transport.requests == chunk_titles.ATTEMPTS


async def test_an_input_above_the_feature_limit_is_never_sent():
    transport = ReplyTransport("Titulek")
    llm = gateway(transport, catalog(max_input_tokens=50))
    assert (await generate_title(llm, messages("slovo " * 400, None, None)))[0] == "too_large"
    assert transport.requests == 0


def test_provenance_records_the_model_and_refuses_an_unusable_catalog(tmp_path):
    path = tmp_path / "models.yaml"
    path.write_text("catalog bytes")
    origin = provenance(gateway(ReplyTransport()), None, path)
    assert origin | {"prompt_sha256": None, "models_config_sha256": None} == {
        "prompt_version": chunk_titles.PROMPT_VERSION, "prompt_sha256": None, "feature": FEATURE, "tier": "tiny",
        "provider": "ollama", "model": "fake-titles", "model_endpoint": "http://fake/ollama",
        "max_input_tokens": 16000, "max_output_tokens": 64, "models_config": str(path.resolve()),
        "models_config_sha256": None}
    assert len(origin["prompt_sha256"]) == 64
    with pytest.raises(Refused, match="OPENAI_API_KEY"):   # checked without a model call
        provenance(gateway(ReplyTransport(), catalog("openai")), None, path)
    without = {"tiers": catalog()["tiers"], "features": {"other": {"default": "tiny"}}}
    with pytest.raises(Refused, match="chunk_titles"):
        provenance(gateway(ReplyTransport(), without), None, path)
    with pytest.raises(Refused, match="tier"):
        provenance(gateway(ReplyTransport()), "large", path)


@pytest.mark.parametrize("name, provider, endpoint", [
    ("chunk_titles_ollama.yaml", "ollama", "http://fake/ollama"),
    # Its own server, never OPENAI_API_URL (another provider) of the environment.
    ("chunk_titles_vllm.yaml", "openai", "http://localhost:8000/v1"),
])
def test_shipped_catalogs_serve_the_feature(name, provider, endpoint):
    path = Path(chunk_titles.__file__).parents[1] / "configs" / name
    llm = LlmGateway(ModelCatalog.load(path), ProviderSettings(
        openai_base_url="https://openrouter.example/api/v1", ollama_base_url="http://fake/ollama",
        openai_api_key="server-key"))
    origin = provenance(llm, None, path)
    assert (origin["provider"], origin["model_endpoint"]) == (provider, endpoint)
    assert (origin["max_input_tokens"], origin["max_output_tokens"]) == (4096, 512)


def result(mode="write", complete=True, **counts):
    return {"mode": mode, "complete": complete, "counts": chunk_titles._counts() | counts}


@pytest.mark.parametrize("summary, code", [
    (result(has_title=3, generate=2, written=2), 0),
    (result("check", has_title=3), 0),
    (result("check", generate=1), 1),                      # something to generate
    (result(generate=2, written=1, deferred_no_document_title=1), 1),
    (result(generate=1, model_failed=1), 1),
    (result(empty_text=1), 1),
    (result(complete=False, generate=1, written=1), 1),   # stopped by --limit
    (result(invalid_output=1), 1),
    (result(write_failed=1), 1),
])
def test_exit_code(summary, code):
    assert exit_code(summary) == code


def test_the_parser_requires_a_models_config_and_reads_selections(tmp_path):
    parser = chunk_titles._parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--check"])
    ids = tmp_path / "chunks.txt"
    ids.write_text(f"{CHUNK}\n")
    args = parser.parse_args(["--check", "--models-config", "m.yaml", "--documents", str(DOC),
                              "--chunks-from", str(ids)])
    assert chunk_titles.selection_from(args) == Selection(True, (DOC,), (CHUNK,))
    args = parser.parse_args(["--check", "--models-config", "m.yaml"])
    assert chunk_titles.selection_from(args) == Selection() and args.check and not args.write
    args = parser.parse_args(["--write", "--models-config", "m.yaml", "--after", str(CHUNK), "--limit", "5"])
    assert (args.after, args.limit, args.report) == (CHUNK, 5, None)
    with pytest.raises(SystemExit):
        parser.parse_args(["--check", "--write", "--models-config", "m.yaml"])


@pytest.mark.parametrize("option", ["--limit", "--concurrency"])
@pytest.mark.parametrize("value", ["0", "-1"])
def test_the_parser_refuses_a_limit_or_concurrency_below_one(option, value):
    with pytest.raises(SystemExit):   # a concurrency of 0 would wait forever
        chunk_titles._parser().parse_args(["--check", "--models-config", "m.yaml", option, value])
