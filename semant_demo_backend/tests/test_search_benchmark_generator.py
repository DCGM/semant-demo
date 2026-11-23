"""The search benchmark dataset generator (#726): sampling, prompts and checks, intents,
translations, pooling, judging with its cache, resumable steps and the CLI.

Model calls go through the real ``LlmGateway`` to the in-process fake provider
(``tests/fake_providers.py``: ``fake_intent``, ``fake_translation``, ``fake_judgement``). The
source store and the benchmark store are in-memory fakes of ``SourceReader`` and
``BenchmarkStore``; the Weaviate source is tested in ``tests/integration/test_search_benchmark_source.py``.
"""
from __future__ import annotations

import json
import uuid
from collections import Counter
from pathlib import Path
from uuid import UUID

import pytest
import yaml
from httpx import ASGITransport

from semant_demo.adapters.llm.gateway import LlmGateway, ProviderSettings
from semant_demo.benchmarks.search_relevance import llm as benchmark_llm
from semant_demo.benchmarks.search_relevance import prompts
from semant_demo.benchmarks.search_relevance.calls import CachedModel
from semant_demo.benchmarks.search_relevance.config import (
    INTENTS_FEATURE, JUDGE_FEATURE, TRANSLATION_FEATURE, GeneratorConfig)
from semant_demo.benchmarks.search_relevance.contracts import SOURCE, CorpusChunk, Intent, Query, load_dataset
from semant_demo.benchmarks.search_relevance.generate import main
from semant_demo.benchmarks.search_relevance.generation import generate_intents, style_counts, translate
from semant_demo.benchmarks.search_relevance.judging import aggregate, judge_pools
from semant_demo.benchmarks.search_relevance.llm import InvalidReply, Refused, UsageTotals
from semant_demo.benchmarks.search_relevance.pipeline import Generator, Resources
from semant_demo.benchmarks.search_relevance.pooling import Candidate, cap_pools, pool_candidates
from semant_demo.benchmarks.search_relevance.sampling import mark_near_duplicates, sample_corpus
from semant_demo.benchmarks.search_relevance.source import MIXED, UNKNOWN, SourceChunk
from semant_demo.benchmarks.search_relevance.store_api import LoadReport, SearchOutcome, VectorReport
from tests.corpus import load_corpus
from tests.fake_providers import create_fake_provider_app

LANGUAGES = ("ces", "eng", "deu")


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(benchmark_llm, "BACKOFF", 0)


# ---- fakes --------------------------------------------------------------------------------

def cid(language: str, document: int, order: int) -> UUID:
    """Ids spread over the UUID space (as random v4 ids are), stable per chunk."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"chunk/{language}/{document}/{order}")


def did(language: str, document: int) -> UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"document/{language}/{document}")


def text(language: str, document: int, order: int) -> str:
    """Distinct words per chunk (``l3d1o2w0`` …), long enough to be sampled."""
    return " ".join(f"{language[0]}{document}o{order}w{i}" for i in range(14))


def source_chunks(documents: int = 4, per_document: int = 8, languages=LANGUAGES, years=(1850, 1910)
                  ) -> list[SourceChunk]:
    found = []
    for language in languages:
        for d in range(documents):
            for o in range(per_document):
                found.append(SourceChunk(id=cid(language, d, o), document_id=did(language, d), order=o,
                                         language=language, text=text(language, d, o), title=None,
                                         document_title=f"Document {language} {d}", year=years[d % len(years)],
                                         document_type="BOOK" if d % 2 else "PERIODICAL"))
    return found


class FakeSource:
    """``SourceReader`` over a list; records its reads (it has no write methods at all)."""

    def __init__(self, chunks: list[SourceChunk]):
        self.chunks = sorted(chunks, key=lambda c: c.id)
        self.reads: Counter[str] = Counter()

    async def languages(self):
        self.reads["languages"] += 1
        return dict(Counter(c.language for c in self.chunks))

    async def scan(self, page):
        self.reads["scan"] += 1
        for chunk in self.chunks:  # in id order
            yield chunk.id, chunk.language

    async def neighbours(self, document_id, orders):
        self.reads["neighbours"] += 1
        return [c for c in self.chunks if c.document_id == document_id and c.order in orders]

    async def read(self, ids):
        self.reads["read"] += 1
        return [c for c in self.chunks if c.id in set(ids)]

    def describe(self):
        return {"fake": "source"}


class FakeStore:
    """``BenchmarkStore``: ``text`` ranks by shared words, ``vector`` by shared character
    trigrams, ``hybrid`` by both; a query containing ``FAKE-SEARCH-FAIL`` fails."""

    def __init__(self):
        self.corpus: dict[UUID, CorpusChunk] = {}
        self.loaded: list[str] = []
        self.vectors: list[str] = []
        self.closed = False

    async def load(self, dataset):
        self.loaded.append(dataset.manifest.dataset_id)
        already = set(self.corpus) == set(dataset.corpus)
        self.corpus = dict(dataset.corpus)
        return LoadReport(dataset.manifest.dataset_id, dataset.manifest.version,
                          chunks_written=0 if already else len(self.corpus), already_loaded=already)

    async def ensure_vector(self, spec, endpoint, cache_dir):
        self.vectors.append(spec.id)
        return VectorReport(spec.target_vector, embedded=len(self.corpus), written=len(self.corpus))

    def searcher(self, configuration, endpoint):
        def score(query: str, chunk: CorpusChunk) -> float:
            words = len(set(query.lower().split()) & set(chunk.text.lower().split()))
            grams = lambda s: {s[i:i + 3] for i in range(len(s) - 2)}  # noqa: E731
            trigrams = len(grams(query.lower()) & grams(chunk.text.lower())) / 10
            return {"text": words, "vector": trigrams, "hybrid": words + trigrams}[configuration.mode]

        async def search(query: str) -> SearchOutcome:
            if "FAKE-SEARCH-FAIL" in query:
                raise ConnectionError("down")
            ranked = sorted(((score(query, c), str(i), i) for i, c in self.corpus.items()), reverse=True)
            return SearchOutcome([(i, s) for s, _, i in ranked if s > 0][:configuration.depth], None, 1.0)
        return search

    async def describe(self):
        return {"weaviate": "fake", "collections": ["Chunks"]}

    async def close(self):
        self.closed = True


def catalog() -> dict:
    return {"tiers": {"tiny": {"provider": "ollama", "model": "fake-benchmark", "price_basis": "local_rate",
                               "input_price": 0, "output_price": 0}},
            "features": {f: {"default": "tiny", "limits": {"max_output_tokens": 256, "max_input_tokens": 8000}}
                         for f in (INTENTS_FEATURE, TRANSLATION_FEATURE, JUDGE_FEATURE)}}


def config(**overrides) -> GeneratorConfig:
    data = {
        "dataset_id": "test-benchmark", "version": "v0", "models": catalog(),
        "sample": {"per_language": 6, "max_per_document": 2, "min_chars": 20, "context_fraction": 0},
        "intents": {"count": 6, "styles": {"keywords": 1, "question": 1}},
        "pooling": {"methods": [
            {"id": "bm25", "mode": "text", "depth": 5},
            {"id": "trigram", "mode": "vector", "depth": 5,
             "vector": {"id": "fake-small", "model": "fake-small", "target_vector": "fake_small"},
             "endpoint": {"base_url": "http://fake/openai/v1"}}],
            "max_candidates_per_intent": 6},
    }
    for key, value in overrides.items():
        data[key] = {**data[key], **value} if isinstance(value, dict) and isinstance(data.get(key), dict) else value
    return GeneratorConfig.model_validate(data)


@pytest.fixture
def usage():
    return UsageTotals()


@pytest.fixture
def gateway(usage):
    return LlmGateway(GeneratorConfig.model_validate(
        {"dataset_id": "x", "version": "v", "models": catalog(),
         "pooling": {"methods": [{"id": "bm25", "mode": "text"}]}}).catalog(),
        ProviderSettings(ollama_base_url="http://fake/ollama", max_retries=0), usage,
        http_transport=ASGITransport(app=create_fake_provider_app(load_corpus())))


def corpus_records(chunks: list[SourceChunk]) -> list[CorpusChunk]:
    return [CorpusChunk(chunk_id=c.id, document_id=c.document_id, order=c.order, language=c.language, text=c.text,
                        attributes={"sampled_by": "random"}) for c in chunks]


# ---- sampling -----------------------------------------------------------------------------

async def test_sampling_balances_languages_caps_documents_and_records_exclusions():
    chunks = source_chunks() + [
        SourceChunk(uuid.uuid4(), did("ces", 0), 90, MIXED, "x" * 50),
        SourceChunk(uuid.uuid4(), did("ces", 0), 91, UNKNOWN, "x" * 50),
        SourceChunk(uuid.uuid4(), did("ces", 0), 92, "fra", "x" * 50),
        SourceChunk(uuid.uuid4(), did("ces", 0), 93, "ces", "short"),
        SourceChunk(uuid.uuid4(), None, 0, "ces", "y" * 50)]
    corpus, report = await sample_corpus(FakeSource(chunks), config(sample={"oversample": 10}))  # reads all

    assert Counter(c.language for c in corpus) == {"ces": 6, "eng": 6, "deu": 6}
    assert max(Counter(c.document_id for c in corpus).values()) <= 2
    for language in LANGUAGES:  # balanced strata: both periods and document types
        periods = {c.attributes["period"] for c in corpus if c.language == language}
        assert periods == {"1850-1874", "1900-1924"}
    assert report["excluded_languages"] == {MIXED: 1, UNKNOWN: 1, "fra": 1}  # counted by the scan, never read
    assert report["read_exclusions"] == {"too_short": 1, "no_document": 1}
    assert report["scanned"] == len(chunks) and report["method"] == "scan + reservoir sample"
    assert report["short"] == {}
    assert all(c.document.title and c.attributes["sampled_by"].startswith("random") for c in corpus)


async def test_sampling_is_deterministic_with_its_seed():
    chunks = source_chunks()
    first, _ = await sample_corpus(FakeSource(chunks), config())
    again, _ = await sample_corpus(FakeSource(chunks), config())
    other, _ = await sample_corpus(FakeSource(chunks), config(seeds={"sample": 7}))
    assert [c.chunk_id for c in first] == [c.chunk_id for c in again]
    assert {c.chunk_id for c in first} != {c.chunk_id for c in other}


async def test_a_rare_language_is_sampled_from_all_its_chunks_and_a_short_one_reported():
    # 1 German chunk in 33: a scan reaches all of them wherever they are, unlike batches or filters.
    common = source_chunks(documents=8, per_document=12, languages=("ces",))
    rare = source_chunks(documents=3, per_document=1, languages=("deu",))
    source = FakeSource(common + rare)
    corpus, report = await sample_corpus(source, config(languages=("ces", "deu"), sample={"oversample": 1}))
    assert source.reads["scan"] == 1 and report["scanned"] == 99
    assert {c.chunk_id for c in corpus if c.language == "deu"} == {c.id for c in rare}  # every one of the 3
    assert report["short"] == {"deu": {"target": 6, "selected": 3}}
    assert report["sampled_ids"] == {"ces": 6, "deu": 3}  # oversample 1: target, or all a language has


async def test_the_reservoir_is_a_uniform_sample_of_the_whole_scan():
    chunks = source_chunks(documents=40, per_document=25, languages=("ces",))  # 1,000 chunks
    first_half = {c.id for c in sorted(chunks, key=lambda c: c.id)[:500]}  # the scan reads in id order
    hits = Counter()
    for seed in range(200):
        corpus, _ = await sample_corpus(FakeSource(chunks), config(
            languages=("ces",), seeds={"sample": seed}, sample={"per_language": 10, "oversample": 1,
                                                                "max_per_document": 25, "strata": "proportional"}))
        hits.update(int(c.chunk_id in first_half) for c in corpus)
    # Half the ids lie in the first half of the scan: about half the sampled chunks must too.
    assert 0.44 < hits[1] / (hits[0] + hits[1]) < 0.56


async def test_sampling_adds_neighbouring_chunks_as_context():
    corpus, report = await sample_corpus(FakeSource(source_chunks()),
                                         config(sample={"context_fraction": 0.5, "context_neighbours": 1}))
    context = [c for c in corpus if c.attributes["sampled_by"] == "context"]
    by_id = {c.chunk_id: c for c in corpus}
    assert context and report["context_added"] == len(context)
    for chunk in context:
        anchor = by_id[UUID(chunk.attributes["context_of"])]
        assert anchor.document_id == chunk.document_id and abs(anchor.order - chunk.order) == 1


def test_near_duplicates_are_kept_and_marked():
    base = " ".join(f"word{i}" for i in range(40))
    chunks = corpus_records([SourceChunk(cid("ces", 0, i), did("ces", 0), i, "ces", t) for i, t in enumerate(
        [base, base + " extra", text("ces", 1, 1)])])
    marked = mark_near_duplicates(chunks)
    first = min((chunks[0].chunk_id, chunks[1].chunk_id), key=str)
    assert [c.attributes.get("near_duplicate_of") for c in marked].count(str(first)) == 1
    assert "near_duplicate_of" not in marked[2].attributes


# ---- prompts and checks -------------------------------------------------------------------

@pytest.mark.parametrize("reply, expected", [
    ('{"need": "A need.", "query": "fire  Lhota"}', {"need": "A need.", "query": "fire Lhota"}),
    ('```json\n{"need": "N", "query": "Q"}\n```', {"need": "N", "query": "Q"}),
])
def test_parse_intent(reply, expected):
    assert prompts.parse_intent(reply) == expected


@pytest.mark.parametrize("reply, reason", [
    ("Here is a query: fire", "not JSON"), ('["x"]', "not a JSON object"), ('{"need": "N"}', "no query"),
    ('{"query": "Q"}', "no need"), ('{"need": "N", "query": "' + "x " * 300 + '"}', "query too long")])
def test_parse_intent_refuses_unusable_replies(reply, reason):
    with pytest.raises(InvalidReply, match=reason):
        prompts.parse_intent(reply)


@pytest.mark.parametrize("reply, grade", [("2", 2), (" 0\n", 0), ("**1**", 1)])
def test_parse_grade(reply, grade):
    assert prompts.parse_grade(reply) == grade


@pytest.mark.parametrize("reply", ["3", "2 because", "", "relevant"])
def test_parse_grade_refuses_other_replies(reply):
    with pytest.raises(InvalidReply):
        prompts.parse_grade(reply)


def test_parse_translation():
    assert prompts.parse_translation('{"translation": " Brand  in Lhota "}') == "Brand in Lhota"
    with pytest.raises(InvalidReply):
        prompts.parse_translation('{"translation": ""}')


def test_near_copy_check():
    passage = "Roku 1848 přijel do Lhoty hejtman Jan Novák a ubytoval se v hostinci U Zlatého jelena."
    assert prompts.is_near_copy("hejtman Novák Lhota 1848", passage, 5) is None
    assert prompts.is_near_copy("Kdy přijel do Lhoty hejtman Jan Novák?", passage, 5) == "přijel do lhoty hejtman jan novák"
    assert prompts.is_near_copy("přijel do Lhoty", "přijel do Lhoty", 5) == "přijel do lhoty"  # all of it


def test_language_plausibility_heuristic():
    assert not prompts.language_doubtful("Wann brannte die Scheune in Lhota?", "deu")
    assert prompts.language_doubtful("Wann brannte die Scheune in Lhota?", "eng")
    assert not prompts.language_doubtful("Kdy vyhořela stodola?", "ces")
    assert not prompts.language_doubtful("Lhota 1850", "eng")  # no signal: not doubtful


def test_style_counts_follow_the_shares():
    assert style_counts(10, {"keywords": 0.5, "question": 0.3, "entity": 0.2}) == {
        "keywords": 5, "question": 3, "entity": 2}
    assert sum(style_counts(7, {"a": 1, "b": 1, "c": 1}).values()) == 7


def test_prompt_versions_are_recorded():
    provenance = prompts.prompt_provenance(prompts.STYLES)
    assert set(provenance) == {"intents", "translation", "judge"}
    assert provenance["judge"]["prompt_version"] == prompts.JUDGE_PROMPT_VERSION


def test_judge_prompt_says_when_the_passage_is_cut():
    long = prompts.judge_messages("need", "query", "x" * 500, None, 100)[1]["content"]
    short = prompts.judge_messages("need", "query", "x" * 50, None, 100)[1]["content"]
    assert "cut: only its first 100 characters" in long and "cut" not in short


# ---- intents and translations -------------------------------------------------------------

async def test_intents_are_balanced_and_near_copies_and_invalid_replies_replaced(tmp_path, gateway):
    chunks = source_chunks(documents=3, per_document=1)  # three chunks per language
    # Two of the Czech chunks give no usable intent, so both are tried and one Czech intent is missing.
    special = {chunks[0].id: "FAKE-COPY " + chunks[0].text, chunks[1].id: "FAKE-INVALID " + chunks[1].text}
    corpus = [c.model_copy(update={"text": special.get(c.chunk_id, c.text)}) for c in corpus_records(chunks)]
    model = CachedModel(gateway, INTENTS_FEATURE, prompts.INTENT_PROMPT_VERSION, tmp_path)
    cfg = config(intents={"count": 6, "styles": {"keywords": 1, "question": 1}, "spare": 1})
    intents, queries, report = await generate_intents(corpus, cfg, model)

    assert Counter(i.source_language for i in intents) == {"ces": 1, "eng": 2, "deu": 2}
    assert Counter(i.style for i in intents if i.source_language != "ces") == {"keywords": 2, "question": 2}
    by_id = {c.chunk_id: c for c in corpus}
    assert not {c for i in intents for c in i.source_chunk_ids} & set(special)
    for intent, query in zip(intents, queries):
        assert query.intent_id == intent.intent_id and query.language == intent.source_language
        assert query.origin == "generated" and intent.need
        assert prompts.is_near_copy(query.text, by_id[intent.source_chunk_ids[0]].text, 5) is None
    assert report["short"] == {"ces": 1}
    assert report["failed_attempts"] == {"near_copy": 1, "invalid_output: not JSON": 1}
    assert report["near_copy_replies"] == 2  # the first reply and the regeneration


async def test_translations_cover_every_language_and_flag_problems(tmp_path, gateway):
    intents = [Intent(intent_id=f"i{n}", style="keywords", need="A need.", source_chunk_ids=(),
                      source_language="ces") for n in range(3)]
    queries = [Query(query_id="i0.ces", intent_id="i0", language="ces", text="stodola Lhota požár"),
               Query(query_id="i1.ces", intent_id="i1", language="ces", text="FAKE-UNTRANSLATABLE věc"),
               Query(query_id="i2.ces", intent_id="i2", language="ces", text="Lhota")]
    model = CachedModel(gateway, TRANSLATION_FEATURE, prompts.TRANSLATION_PROMPT_VERSION, tmp_path)
    kept, all_queries, report = await translate(intents, queries, config(translation={
        "back_translate_fraction": 1.0}), model)

    assert [i.intent_id for i in kept] == ["i0", "i2"] and report["dropped_intents"] == ["i1"]
    i0 = {q.language: q for q in all_queries if q.intent_id == "i0"}
    assert set(i0) == set(LANGUAGES)
    assert i0["deu"].origin == "translated" and i0["deu"].translated_from == "i0.ces"
    assert i0["eng"].text == "stodola Lhota požár the"
    assert report["back_translation"]["checked"] == 4
    assert report["flags"].get("language_doubtful", []) == []


# ---- pooling ------------------------------------------------------------------------------

def test_caps_keep_source_chunks_and_fit_the_budget():
    ids = [uuid.UUID(int=n) for n in range(10)]
    pools = {"a": [Candidate(ids[0], {SOURCE}), *(Candidate(i, {"bm25"}, best_rank=r) for r, i in
                                                  enumerate(ids[1:6], 1))],
             "b": [Candidate(ids[6], {SOURCE}, best_rank=9), Candidate(ids[7], {"bm25", "vec"}, best_rank=2),
                   Candidate(ids[8], {"vec"}, best_rank=2), Candidate(ids[9], {"bm25"}, best_rank=1)]}
    capped, cap = cap_pools(pools, 3, None)
    assert cap == 3
    assert [c.chunk_id for c in capped["a"]] == ids[0:3]
    assert [c.chunk_id for c in capped["b"]] == [ids[6], ids[9], ids[7]]  # rank, then more methods
    capped, cap = cap_pools(pools, 3, budget=4)
    assert cap == 2 and sum(map(len, capped.values())) == 4
    capped, cap = cap_pools(pools, 3, budget=2)  # down to the sources alone, which are never cut
    assert [len(c) for c in capped.values()] == [1, 1] and cap == 1
    with pytest.raises(Refused, match="max_judgments 1 is below the 2 source chunks"):
        cap_pools(pools, 3, budget=1)  # never more judgments than the budget


async def test_pooling_unions_methods_and_queries_with_the_source(tmp_path):
    from semant_demo.benchmarks.search_relevance.contracts import write_dataset

    chunks = corpus_records(source_chunks(documents=2, per_document=3))
    dataset = write_dataset(tmp_path / "corpus", {"dataset_id": "test-benchmark", "version": "v0"}, chunks,
                            [], [], [])
    source = chunks[0]
    intent = Intent(intent_id="i0", style="keywords", need="N", source_chunk_ids=(source.chunk_id,),
                    source_language="ces")
    other = chunks[7]
    queries = [Query(query_id="i0.ces", intent_id="i0", language="ces", text=source.text.split()[0]),
               Query(query_id="i0.eng", intent_id="i0", language="eng", text=other.text.split()[0],
                     origin="translated", translated_from="i0.ces"),
               Query(query_id="i0.deu", intent_id="i0", language="deu", text="FAKE-SEARCH-FAIL",
                     origin="translated", translated_from="i0.ces")]
    store = FakeStore()
    pools, report = await pool_candidates(store, dataset, [intent], queries, config(), tmp_path / "emb")

    by_id = {c.chunk_id: c for c in pools["i0"]}
    assert by_id[source.chunk_id].methods_order[0] == SOURCE
    assert {"bm25", "trigram"} <= by_id[source.chunk_id].methods
    assert "bm25" in by_id[other.chunk_id].methods  # found by the English query only
    assert len(pools["i0"]) <= 6
    assert report["failed_searches"] == {"bm25": {"ConnectionError": 1}, "trigram": {"ConnectionError": 1}}
    assert store.vectors == ["fake-small"] and report["load"]["chunks_written"] == len(chunks)


# ---- judging ------------------------------------------------------------------------------

def test_grade_aggregation():
    assert aggregate({"ces": 2, "eng": 1, "deu": 2}, "ces", "median") == 2
    assert aggregate({"ces": 2, "eng": 1}, "ces", "median") == 1  # the lower median
    assert aggregate({"ces": 2, "eng": 0, "deu": 1}, "ces", "min") == 0
    assert aggregate({"ces": 2, "eng": 0, "deu": 1}, "ces", "source") == 2


async def test_judging_is_cached_per_language_and_flags_source_problems(tmp_path, gateway, usage):
    chunks = corpus_records(source_chunks(documents=1, per_document=3, languages=("ces",)))
    chunks[2] = chunks[2].model_copy(update={"text": "FAKE-IRRELEVANT " + chunks[2].text})
    corpus = {c.chunk_id: c for c in chunks}
    words = chunks[0].text.split()
    intents = [Intent(intent_id="i0", style="keywords", need="N", source_chunk_ids=(chunks[0].chunk_id,),
                      source_language="ces"),
               Intent(intent_id="i1", style="keywords", need="N", source_chunk_ids=(chunks[2].chunk_id,),
                      source_language="ces")]
    queries = [Query(query_id="i0.ces", intent_id="i0", language="ces", text=f"{words[0]} {words[2]}"),
               Query(query_id="i0.eng", intent_id="i0", language="eng", text=f"{words[0]} {words[2]} the",
                     origin="translated", translated_from="i0.ces"),
               Query(query_id="i1.ces", intent_id="i1", language="ces", text=words[0])]
    pools = {"i0": [{"chunk_id": str(chunks[0].chunk_id), "pooled_by": ["source", "bm25"]},
                    {"chunk_id": str(chunks[1].chunk_id), "pooled_by": ["bm25"]}],
             "i1": [{"chunk_id": str(chunks[2].chunk_id), "pooled_by": ["source"]}]}
    cfg = config(judge={"per_language_fraction": 1.0})

    model = CachedModel(gateway, JUDGE_FEATURE, prompts.JUDGE_PROMPT_VERSION, tmp_path)
    qrels, dropped, report = await judge_pools(intents, queries, pools, corpus, cfg, model)
    grades = {(q.intent_id, q.chunk_id): q for q in qrels}
    source = grades[("i0", chunks[0].chunk_id)]
    assert source.language_grades == {"ces": 2, "eng": 1} and source.grade == 1 and not source.consistent
    assert source.pooled_by == ("source", "bm25")
    assert grades[("i1", chunks[2].chunk_id)].grade == 0
    assert report["source_graded_0"] == ["i1"] and dropped == []
    assert report["per_language"]["inconsistent"] >= 1
    calls = usage.totals["calls"]
    assert calls == report["calls"] == 5

    again = CachedModel(gateway, JUDGE_FEATURE, prompts.JUDGE_PROMPT_VERSION, tmp_path)
    second, _, second_report = await judge_pools(intents, queries, pools, corpus, cfg, again)
    assert usage.totals["calls"] == calls  # all from the cache
    assert second_report["model_calls"] == {"asked": 0, "cached": 5, "failed": 0, "failure_reasons": {}}
    assert second == qrels


async def test_an_intent_whose_source_chunk_cannot_be_judged_is_dropped(tmp_path, gateway, monkeypatch):
    chunks = corpus_records(source_chunks(documents=1, per_document=1, languages=("ces",)))
    intent = Intent(intent_id="i0", style="keywords", need="N", source_chunk_ids=(chunks[0].chunk_id,),
                    source_language="ces")
    query = Query(query_id="i0.ces", intent_id="i0", language="ces", text="x")
    model = CachedModel(gateway, JUDGE_FEATURE, prompts.JUDGE_PROMPT_VERSION, tmp_path)

    async def failing(*args, **kwargs):
        return None, "model_failed: ConnectError"
    monkeypatch.setattr(model, "ask", failing)
    qrels, dropped, report = await judge_pools(
        [intent], [query], {"i0": [{"chunk_id": str(chunks[0].chunk_id), "pooled_by": ["source"]}]},
        {c.chunk_id: c for c in chunks}, config(), model)
    assert qrels == [] and dropped == ["i0"] and report["unjudged"] == {"model_failed: ConnectError": 1}


# ---- the pipeline -------------------------------------------------------------------------

def write_config(path: Path, cfg: GeneratorConfig) -> tuple[GeneratorConfig, dict, str]:
    data = cfg.model_dump(mode="json", by_alias=True, exclude_none=True)
    path.write_text(yaml.safe_dump(data))
    from semant_demo.benchmarks.search_relevance.config import load_config
    return load_config(path)


def generator(tmp_path, gateway, usage, cfg: GeneratorConfig, source: FakeSource, store: FakeStore) -> Generator:
    loaded, data, sha = write_config(tmp_path / "config.yaml", cfg)

    async def open_source():
        return source

    async def open_store(spec):
        return store
    return Generator(loaded, data, sha, tmp_path / "work", tmp_path / "dataset",
                     Resources(llm=gateway, usage=usage, source=open_source, open_store=open_store))


PIPELINE = dict(sample={"per_language": 4, "max_per_document": 2, "min_chars": 20, "context_fraction": 0.25},
                judge={"per_language_fraction": 0.5}, translation={"back_translate_fraction": 0.5})


async def test_the_pipeline_writes_a_valid_dataset_and_resumes_without_model_calls(tmp_path, gateway, usage):
    source, store = FakeSource(source_chunks()), FakeStore()
    cfg = config(**PIPELINE)
    ran = await generator(tmp_path, gateway, usage, cfg, source, store).run()
    assert ran == ["sample", "intents", "translate", "pool", "judge", "write"]
    assert store.closed

    dataset = load_dataset(tmp_path / "dataset")
    assert Counter(c.language for c in dataset.corpus.values() if c.attributes["sampled_by"] != "context") == {
        "ces": 4, "eng": 4, "deu": 4}
    assert len(dataset.intents) == 6
    assert Counter(q.language for q in dataset.queries.values()) == {"ces": 6, "eng": 6, "deu": 6}
    for intent in dataset.intents.values():
        graded = {q.chunk_id: q for q in dataset.qrels if q.intent_id == intent.intent_id}
        assert all(SOURCE in graded[c].pooled_by for c in intent.source_chunk_ids)
    m = dataset.manifest
    assert [p.id for p in m.pooling] == ["bm25", "trigram"] and len(m.judges) == 1
    assert m.models["judge"]["prompt_version"] == prompts.JUDGE_PROMPT_VERSION
    assert m.models["intents"]["model"] == "fake-benchmark"
    assert m.store_schema == {"weaviate": "fake", "collections": ["Chunks"]}
    assert m.config["sha256"] and m.seeds == {"sample": 0, "intents": 0, "judge": 0}
    assert m.generator["usage"]["calls"] == usage.totals["calls"] > 0
    assert any("Pooling is incomplete" in item for item in m.limitations)
    assert m.source["fake"] == "source"
    summary = (tmp_path / "dataset" / "summary.md").read_text()
    assert "## Language balance" in summary and "## Judgements" in summary

    # A second run skips every step; a forced judge step asks the cache, not the model.
    calls, reads = usage.totals["calls"], sum(source.reads.values())
    again = generator(tmp_path, gateway, usage, cfg, source, store)
    assert await again.run() == []
    assert await again.run(start="judge") == ["judge", "write"]
    assert usage.totals["calls"] == calls and sum(source.reads.values()) == reads
    assert load_dataset(tmp_path / "dataset").qrels == dataset.qrels

    # A changed judge setting reruns the judge and the writing only.
    changed = generator(tmp_path, gateway, usage, config(**{**PIPELINE, "judge": {"per_language_fraction": 0}}),
                        source, store)
    assert await changed.run() == ["judge", "write"]
    assert all(q.language_grades is None for q in load_dataset(tmp_path / "dataset").qrels)

    # A smaller pool keeps the corpus, intents and translations; its judgements are all cached.
    smaller = generator(tmp_path, gateway, usage, config(**{**PIPELINE, "judge": {"per_language_fraction": 0},
                                                            "pooling": {"max_candidates_per_intent": 2}}),
                        source, store)
    assert await smaller.run() == ["pool", "judge", "write"]
    assert usage.totals["calls"] == calls
    assert Counter(q.intent_id for q in load_dataset(tmp_path / "dataset").qrels) == {i: 2 for i in dataset.intents}


async def test_imported_intents_bring_their_source_chunks(tmp_path, gateway, usage):
    chunks = source_chunks()
    outside = chunks[5]  # in the store; the sample includes it because an import names it
    imports = tmp_path / "imports.jsonl"
    imports.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
        {"question": "Kdo přijel do Lhoty?", "corpus_id": str(outside.id), "language": "cs"},
        {"question": "Where is it?", "language": "en"},
        {"question": "", "language": "en"}]) + "\n")
    cfg = config(**PIPELINE, intents={"count": 3, "styles": {"keywords": 1},
                                      "import": {"path": str(imports)}})
    await generator(tmp_path, gateway, usage, cfg, FakeSource(chunks), FakeStore()).run()
    dataset = load_dataset(tmp_path / "dataset")
    imported = [i for i in dataset.intents.values() if i.origin == "imported"]
    assert len(imported) == 2
    with_source = next(i for i in imported if i.source_chunk_ids)
    assert with_source.source_chunk_ids == (outside.id,) and with_source.need == "Kdo přijel do Lhoty?"
    assert dataset.corpus[outside.id].attributes["sampled_by"] in ("imported", "random")
    assert {q.origin for q in dataset.queries.values() if q.intent_id == with_source.intent_id} == {
        "imported", "translated"}
    assert dataset.manifest.checks["intents"]["imports"]["skipped"]["no_text"] == 1


# ---- the command --------------------------------------------------------------------------

def test_validate_prints_the_summary(tmp_path, capsys):
    from tests import search_benchmark_fixture as fixture
    fixture.build_dataset(tmp_path / "dataset")
    assert main(["validate", str(tmp_path / "dataset")]) == 0
    assert "# Search benchmark dataset `fixture` v0" in capsys.readouterr().out
    (tmp_path / "dataset" / "qrels.jsonl").write_text("")
    assert main(["validate", str(tmp_path / "dataset")]) == 2


def test_budget_estimates_without_calls(tmp_path, capsys):
    write_config(tmp_path / "config.yaml", config(judge={"per_language_fraction": 0.5}))
    assert main(["budget", str(tmp_path / "config.yaml")]) == 0
    estimate = json.loads(capsys.readouterr().out)
    assert estimate["calls"][INTENTS_FEATURE]["expected"] == 6
    assert estimate["calls"][TRANSLATION_FEATURE]["expected"] == 12
    assert estimate["calls"][JUDGE_FEATURE]["expected"] == 6 * 6 * 2
    assert estimate["cost_usd"] == 0


def test_a_configuration_without_the_features_is_refused(tmp_path, capsys):
    data = config().model_dump(mode="json", by_alias=True, exclude_none=True)
    del data["models"]["features"][JUDGE_FEATURE]
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(data))
    assert main(["budget", str(tmp_path / "config.yaml")]) == 2
    assert "search_benchmark_judge" in capsys.readouterr().err


def test_the_example_configuration_is_valid():
    from semant_demo.benchmarks.search_relevance.config import load_config
    path = Path(__file__).parents[1] / "semant_demo" / "configs" / "search_benchmark_generator.yaml"
    cfg, _, _ = load_config(path)
    assert cfg.languages == LANGUAGES and cfg.intents.count == 210


def test_the_command_line_source_is_part_of_the_sample_steps_inputs(tmp_path, gateway, usage):
    from argparse import Namespace

    from semant_demo.benchmarks.search_relevance.generate import with_source_overrides
    cfg = config()
    none = Namespace(source_host=None, source_port=None, source_grpc_port=None)
    assert with_source_overrides(cfg, none) is cfg
    moved = with_source_overrides(cfg, Namespace(source_host="127.0.0.1", source_port=18080, source_grpc_port=15051))
    assert (moved.source.host, moved.source.rest_port, moved.source.grpc_port) == ("127.0.0.1", 18080, 15051)

    def sample_inputs(c):
        return generator(tmp_path, gateway, usage, c, FakeSource(source_chunks()), FakeStore()).inputs("sample")
    assert sample_inputs(cfg) != sample_inputs(moved)  # another store reruns the sampling


def test_near_duplicates_are_found_although_the_buckets_first_member_differs():
    base = " ".join(f"word{i}" for i in range(60))
    other = " ".join(f"other{i}" for i in range(60))
    # B and C are near-duplicates; A, sorted first, shares no shingle with them.
    chunks = corpus_records([SourceChunk(cid("ces", 0, i), did("ces", 0), i, "ces", t) for i, t in enumerate(
        [other, base, base + " extra"])])
    marked = mark_near_duplicates(chunks)
    first = min((chunks[1].chunk_id, chunks[2].chunk_id), key=str)
    assert sorted(c.attributes.get("near_duplicate_of") or "" for c in marked) == ["", "", str(first)]


async def test_a_cache_line_cut_by_an_interruption_is_dropped_and_rewritten(tmp_path, gateway):
    model = CachedModel(gateway, INTENTS_FEATURE, prompts.INTENT_PROMPT_VERSION, tmp_path)
    good = json.dumps({"key": "k1", "reply": "r1"})
    model.path.write_text(good + "\n" + '{"key": "k2", "re', encoding="utf-8")  # the process died mid-line
    reopened = CachedModel(gateway, INTENTS_FEATURE, prompts.INTENT_PROMPT_VERSION, tmp_path)
    assert reopened.replies == {"k1": "r1"}
    assert model.path.read_text(encoding="utf-8") == good + "\n"  # the next reply starts on a new line


def test_budget_counts_an_output_without_fresh_state_as_still_to_run(tmp_path, capsys):
    write_config(tmp_path / "config.yaml", config(judge={"per_language_fraction": 0.5}))
    work = tmp_path / "work"
    (work / "intents").mkdir(parents=True)
    intent = Intent(intent_id="i0", style="keywords", need="A need.", source_language="ces")
    (work / "intents" / "intents.jsonl").write_text(intent.model_dump_json() + "\n", encoding="utf-8")
    assert main(["budget", str(tmp_path / "config.yaml"), "--work", str(work)]) == 0
    estimate = json.loads(capsys.readouterr().out)
    assert estimate["done_steps"] == [] and estimate["intents"] == 1  # the file sizes the estimate only
    assert estimate["calls"][INTENTS_FEATURE]["expected"] == 6  # run would generate again
    assert estimate["calls"][TRANSLATION_FEATURE]["expected"] == 2  # one intent into two languages


def other_judge_gateway(usage) -> tuple[GeneratorConfig, LlmGateway]:
    """The pipeline's configuration with another judge model, and its gateway."""
    models = catalog()
    models["tiers"]["small"] = {**models["tiers"]["tiny"], "model": "fake-other-judge"}
    models["features"][JUDGE_FEATURE] = {**models["features"][JUDGE_FEATURE], "default": "small"}
    cfg = config(**PIPELINE, models=models)
    return cfg, LlmGateway(cfg.catalog(), ProviderSettings(ollama_base_url="http://fake/ollama", max_retries=0),
                           usage, http_transport=ASGITransport(app=create_fake_provider_app(load_corpus())))


async def test_budget_counts_only_the_steps_run_would_redo(tmp_path, gateway, usage):
    from semant_demo.benchmarks.search_relevance.budget import estimate
    cfg = config(**PIPELINE)
    await generator(tmp_path, gateway, usage, cfg, FakeSource(source_chunks()), FakeStore()).run()
    work = tmp_path / "work"
    fresh = estimate(cfg, work, gateway)
    assert fresh["done_steps"] == ["intents", "translate", "judge"]
    assert all(entry["expected"] == 0 for entry in fresh["calls"].values())

    changed, other = other_judge_gateway(usage)  # another judge model: run would judge again
    redo = estimate(changed, work, other)
    assert redo["done_steps"] == ["intents", "translate"]
    assert redo["calls"][JUDGE_FEATURE]["expected"] == fresh["judged_pairs"] * 2 > 0  # per-language bound
    assert redo["calls"][JUDGE_FEATURE]["model"] == "fake-other-judge"
    assert estimate(cfg, work)["done_steps"] == []  # without the gateway nothing is known to be fresh


def test_the_recorded_command_names_no_paths_hosts_or_ports():
    from semant_demo.benchmarks.search_relevance.pipeline import recorded_command
    argv = ["/home/alice/semant/generate.py", "run", "/home/alice/v1.yaml", "--work", "/home/alice/work",
            "--source-host", "prod.internal", "--source-port", "8080", "--from", "judge", "--force"]
    assert recorded_command(argv) == "generate run --from judge --force"


# ---- review fixes -------------------------------------------------------------------------

VECTOR = {"id": "fake-small", "model": "fake-small", "target_vector": "fake_small"}


def methods(*extra: dict) -> dict:
    return {"methods": [{"id": "bm25", "mode": "text", "depth": 5}, *extra]}


def test_api_key_env_must_name_a_variable_not_hold_a_key():
    with pytest.raises(ValueError, match="api_key_env"):
        config(pooling=methods({"id": "vec", "mode": "vector", "vector": VECTOR,
                                "endpoint": {"base_url": "http://fake/v1", "api_key_env": "sk-pasted-secret-key"}}))
    named = config(pooling=methods({"id": "vec", "mode": "vector", "vector": VECTOR,
                                    "endpoint": {"base_url": "http://fake/v1", "api_key_env": "EMBEDDING_KEY"}}))
    assert named.pooling.methods[1].endpoint.api_key_env == "EMBEDDING_KEY"


async def test_pooling_is_refused_when_the_named_key_is_not_set(tmp_path, gateway, usage, monkeypatch):
    monkeypatch.delenv("SEMANT_TEST_EMBEDDING_KEY", raising=False)
    cfg = config(**PIPELINE, pooling=methods({
        "id": "vec", "mode": "vector", "vector": VECTOR,
        "endpoint": {"base_url": "http://fake/v1", "api_key_env": "SEMANT_TEST_EMBEDDING_KEY"}}))
    store = FakeStore()
    with pytest.raises(Refused, match="SEMANT_TEST_EMBEDDING_KEY is not set"):
        await generator(tmp_path, gateway, usage, cfg, FakeSource(source_chunks()), store).run()
    assert store.loaded == []  # refused before the store is touched
    monkeypatch.setenv("SEMANT_TEST_EMBEDDING_KEY", "x")
    assert await generator(tmp_path, gateway, usage, cfg, FakeSource(source_chunks()), store).run() == [
        "pool", "judge", "write"]


async def test_identical_asks_in_flight_make_one_call(tmp_path, gateway, usage):
    import asyncio
    model = CachedModel(gateway, JUDGE_FEATURE, prompts.JUDGE_PROMPT_VERSION, tmp_path)
    messages = prompts.judge_messages("need", "Lhota", "Lhota stodola", None, 1000)
    results = await asyncio.gather(*(model.ask(messages, prompts.parse_grade) for _ in range(3)))
    assert len(set(results)) == 1 and results[0][1] is None
    assert usage.totals["calls"] == 1
    assert model.report()["asked"] == 1 and model.report()["cached"] == 2
    assert len(model.path.read_text(encoding="utf-8").splitlines()) == 1
    assert await model.ask(messages, prompts.parse_grade) == results[0] and usage.totals["calls"] == 1


async def test_a_failed_call_in_flight_is_shared_but_not_cached(tmp_path, gateway, monkeypatch):
    import asyncio
    model = CachedModel(gateway, JUDGE_FEATURE, prompts.JUDGE_PROMPT_VERSION, tmp_path)
    calls = []

    async def failing(llm, feature, messages, parse):
        calls.append(1)
        await asyncio.sleep(0)
        return None, "model_failed: ConnectError"
    monkeypatch.setattr("semant_demo.benchmarks.search_relevance.calls.ask", failing)
    messages = prompts.judge_messages("need", "q", "text", None, 1000)
    assert await asyncio.gather(model.ask(messages, prompts.parse_grade), model.ask(messages, prompts.parse_grade)
                                ) == [(None, "model_failed: ConnectError")] * 2
    assert len(calls) == 1 and model.report()["failed"] == 1
    await model.ask(messages, prompts.parse_grade)
    assert len(calls) == 2  # a failure is asked again later


def test_a_last_cache_line_without_its_newline_gets_one(tmp_path, gateway):
    model = CachedModel(gateway, INTENTS_FEATURE, prompts.INTENT_PROMPT_VERSION, tmp_path)
    good = json.dumps({"key": "k1", "reply": "r1"})
    model.path.write_text(good, encoding="utf-8")  # killed between the JSON and its newline
    reopened = CachedModel(gateway, INTENTS_FEATURE, prompts.INTENT_PROMPT_VERSION, tmp_path)
    assert reopened.replies == {"k1": "r1"}
    assert model.path.read_text(encoding="utf-8") == good + "\n"  # the next reply starts on a new line


def test_the_import_selection_is_part_of_the_sample_steps_inputs(tmp_path, gateway, usage):
    chunks = source_chunks()
    imports = tmp_path / "imports.jsonl"
    imports.write_text("".join(json.dumps({"question": f"Q{n}?", "corpus_id": str(chunks[n].id), "language": "cs"})
                               + "\n" for n in range(4)))

    def sample_inputs(top=None, **imported):
        cfg = config(intents={"import": {"path": str(imports), **imported}}, **(top or {}))
        return generator(tmp_path, gateway, usage, cfg, FakeSource(chunks), FakeStore()).inputs("sample")
    everything = sample_inputs()
    assert len(everything["imports"]) == 4
    assert sample_inputs(limit=2) != everything  # fewer imports: fewer source chunks sampled
    assert sample_inputs(limit=2) != sample_inputs(limit=2, top={"seeds": {"intents": 5}})
    assert sample_inputs(top={"query_languages": ("eng", "deu")})["imports"] == []  # Czech not queried


async def test_an_imported_source_chunk_without_a_document_is_reported_missing():
    orphan = SourceChunk(uuid.uuid4(), None, 0, "ces", "y" * 50)
    corpus, report = await sample_corpus(FakeSource(source_chunks() + [orphan]), config(), [orphan.id])
    assert orphan.id not in {c.chunk_id for c in corpus}
    assert report["imported_sources_missing"] == [str(orphan.id)]


def test_methods_sharing_a_vector_id_must_share_its_spec():
    endpoint = {"base_url": "http://fake/v1"}
    same = {"id": "vec", "mode": "vector", "vector": VECTOR, "endpoint": endpoint}
    hybrid = {"id": "hyb", "mode": "hybrid", "alpha": 0.5, "vector": VECTOR, "endpoint": endpoint}
    assert len(config(pooling=methods(same, hybrid)).pooling.methods) == 3
    with pytest.raises(ValueError, match="sharing a vector id must share its whole spec"):
        config(pooling=methods(same, {**hybrid, "vector": {**VECTOR, "document_template": "{title} {text}"}}))


@pytest.mark.parametrize("extra", [{"vector": VECTOR}, {"endpoint": {"base_url": "http://fake/v1"}}])
def test_a_text_method_takes_no_vector_or_endpoint(extra):
    with pytest.raises(ValueError, match="a text method takes no vector or endpoint"):
        config(pooling=methods({"id": "bm25-plus", "mode": "text", **extra}))


@pytest.mark.parametrize("aggregation", ["median", "source"])
async def test_a_language_whose_judgement_failed_is_counted_and_not_graded(tmp_path, gateway, monkeypatch,
                                                                             aggregation):
    chunks = corpus_records(source_chunks(documents=1, per_document=2, languages=("ces",)))
    intents = [Intent(intent_id="i0", style="keywords", need="N", source_chunk_ids=(chunks[0].chunk_id,),
                      source_language="ces")]
    queries = [Query(query_id="i0.ces", intent_id="i0", language="ces", text="dotaz"),
               *(Query(query_id=f"i0.{lang}", intent_id="i0", language=lang, text=f"query {lang}",
                       origin="translated", translated_from="i0.ces") for lang in ("eng", "deu"))]
    pools = {"i0": [{"chunk_id": str(chunks[0].chunk_id), "pooled_by": ["source"]},
                    {"chunk_id": str(chunks[1].chunk_id), "pooled_by": ["bm25"]}]}
    model = CachedModel(gateway, JUDGE_FEATURE, prompts.JUDGE_PROMPT_VERSION, tmp_path)

    async def ask(messages, parse):  # English always fails; Czech fails for the second chunk
        content = messages[-1]["content"]
        if "query eng" in content or ("dotaz" in content and chunks[1].text in content):
            return None, "model_failed: ConnectError"
        return (1 if "query deu" in content else 2), None
    monkeypatch.setattr(model, "ask", ask)
    qrels, dropped, report = await judge_pools(intents, queries, pools, {c.chunk_id: c for c in chunks},
                                               config(judge={"per_language_fraction": 1.0,
                                                             "aggregation": aggregation}), model)
    assert report["failed_judgements"] == {"model_failed: ConnectError": 3}  # every failed language
    by_chunk = {q.chunk_id: q for q in qrels}
    source = by_chunk[chunks[0].chunk_id]
    assert source.language_grades == {"ces": 2, "deu": 1} and not source.consistent  # the judged ones only
    assert source.grade == (2 if aggregation == "source" else 1)
    if aggregation == "source":  # no Czech grade: unjudged, German does not stand in
        assert chunks[1].chunk_id not in by_chunk
        assert report["unjudged"] == {"model_failed: ConnectError": 1}
        assert report["per_language"]["incomplete"] == 1
    else:
        assert by_chunk[chunks[1].chunk_id].language_grades == {"deu": 1}
        assert by_chunk[chunks[1].chunk_id].consistent
        assert report["unjudged"] == {} and report["per_language"]["incomplete"] == 2
    assert dropped == []


def test_the_command_refuses_a_missing_key_before_any_step(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SEMANT_TEST_EMBEDDING_KEY", raising=False)
    cfg = config(pooling=methods({"id": "vec", "mode": "vector", "vector": VECTOR,
                                  "endpoint": {"base_url": "http://fake/v1", "api_key_env": "SEMANT_TEST_EMBEDDING_KEY"}}))
    write_config(tmp_path / "config.yaml", cfg)
    assert main(["run", str(tmp_path / "config.yaml"), "--work", str(tmp_path / "work")]) == 2
    assert "SEMANT_TEST_EMBEDDING_KEY is not set" in capsys.readouterr().err
    assert not (tmp_path / "work").exists()  # no step ran, no model was called


def test_budget_takes_the_same_source_options_as_run(tmp_path, capsys):
    write_config(tmp_path / "config.yaml", config())
    assert main(["budget", str(tmp_path / "config.yaml"), "--source-host", "127.0.0.1", "--source-port", "18080",
                 "--source-grpc-port", "15051"]) == 0
    assert "calls" in json.loads(capsys.readouterr().out)


async def test_oversampling_lets_the_document_cap_reach_the_target():
    # Ten chunks per document and at most one per document: the target needs ids from many documents.
    chunks = source_chunks(documents=30, per_document=10, languages=("ces",))
    cfg = config(languages=("ces",), sample={"per_language": 6, "max_per_document": 1, "oversample": 4})
    corpus, report = await sample_corpus(FakeSource(chunks), cfg)
    assert len(corpus) == 6 and max(Counter(c.document_id for c in corpus).values()) == 1
    assert report["short"] == {}
