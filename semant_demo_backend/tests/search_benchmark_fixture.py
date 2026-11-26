"""A tiny synthetic search benchmark: a dataset and one run that follow the contract
(``semant_demo/benchmarks/search_relevance/contracts.py``), for the tests of every stage.

Nine chunks (three each in Czech, English and German), three intents (one written from a chunk of
each language), each with a query in all three languages, graded chunks and a run of two
configurations. Write it to a directory with::

    python -m tests.search_benchmark_fixture OUT     # OUT/dataset and OUT/runs/fixture-run
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from semant_demo.benchmarks.search_relevance.contracts import (
    CorpusChunk, Dataset, DocumentInfo, Hit, Intent, Qrel, Query, Run, RunResult, VectorSpec, write_dataset,
    write_run)

CREATED = datetime(2026, 11, 20, tzinfo=timezone.utc)
JUDGE = "fixture-judge"


def chunk_id(n: int) -> UUID:
    return UUID(f"5e3b0000-0000-4000-8000-{n:012d}")


def document_id(n: int) -> UUID:
    return UUID(f"5e3b0000-0000-4000-8000-1{n:011d}")


TEXTS = {
    "ces": ["Dne 12. března vyhořela v obci Lhota stodola sedláka Nováka.",
            "Na trhu v Brně se prodávalo obilí za vyšší ceny než loni.",
            "Obecní rada rozhodla o stavbě nové školy u kostela."],
    "eng": ["A fire destroyed the barn of farmer Novak in the village of Lhota on 12 March.",
            "Grain prices at the Brno market rose above last year's level.",
            "The railway between Prague and Vienna was opened to passengers."],
    "deu": ["Am 12. März brannte in Lhota die Scheune des Bauern Novak nieder.",
            "Die Eisenbahn zwischen Prag und Wien wurde für Reisende eröffnet.",
            "Der Gemeinderat beschloss den Bau einer neuen Schule bei der Kirche."],
}


def corpus() -> list[CorpusChunk]:
    found = []
    for d, (language, texts) in enumerate(TEXTS.items()):
        for order, text in enumerate(texts):
            n = d * 3 + order + 1
            found.append(CorpusChunk(
                chunk_id=chunk_id(n), document_id=document_id(d + 1), order=order, language=language, text=text,
                title=None if order == 2 else f"Title {n}",
                document=DocumentInfo(title=f"Document {language}", year=1900 + d, document_type="PERIODICAL"),
                attributes={"stratum": language, "ocr_quality": "good" if order else "poor"}))
    return found


INTENTS = [
    Intent(intent_id="fire-lhota", style="question", need="Where and when did farmer Novak's barn burn down?",
           source_chunk_ids=(chunk_id(1),), source_language="ces"),
    Intent(intent_id="railway-vienna", style="keywords", need="The opening of the Prague-Vienna railway.",
           source_chunk_ids=(chunk_id(6),), source_language="eng"),
    Intent(intent_id="school-council", style="entity", need="The council's decision to build a school.",
           source_chunk_ids=(chunk_id(9),), source_language="deu"),
]

QUERY_TEXTS = {
    "fire-lhota": {"ces": "Kdy vyhořela stodola v Lhotě?", "eng": "When did the barn in Lhota burn?",
                   "deu": "Wann brannte die Scheune in Lhota?"},
    "railway-vienna": {"ces": "železnice Praha Vídeň otevření", "eng": "Prague Vienna railway opening",
                       "deu": "Eisenbahn Prag Wien Eröffnung"},
    "school-council": {"ces": "obecní rada nová škola", "eng": "council new school", "deu": "Gemeinderat neue Schule"},
}


def queries() -> list[Query]:
    found = []
    for intent in INTENTS:
        original = f"{intent.intent_id}.{intent.source_language}"
        for language, text in QUERY_TEXTS[intent.intent_id].items():
            query_id = f"{intent.intent_id}.{language}"
            translated = language != intent.source_language
            found.append(Query(query_id=query_id, intent_id=intent.intent_id, language=language, text=text,
                               origin="translated" if translated else "generated",
                               translated_from=original if translated else None))
    return found


def qrels() -> list[Qrel]:
    graded = [("fire-lhota", 1, 2, ("source", "bm25")), ("fire-lhota", 4, 2, ("vector",)),
              ("fire-lhota", 7, 2, ("vector",)), ("fire-lhota", 2, 0, ("bm25",)),
              ("railway-vienna", 6, 2, ("source", "vector")), ("railway-vienna", 8, 2, ("bm25", "vector")),
              ("railway-vienna", 5, 0, ("vector",)),
              ("school-council", 9, 2, ("source", "bm25")), ("school-council", 3, 2, ("vector",)),
              ("school-council", 1, 0, ("bm25",))]
    found = [Qrel(intent_id=i, chunk_id=chunk_id(n), grade=g, judge=JUDGE, pooled_by=p) for i, n, g, p in graded]
    # One intent judged per query language, with a disagreement.
    found[2] = found[2].model_copy(update={"grade": 1, "language_grades": {"ces": 2, "eng": 1, "deu": 1},
                                           "consistent": False})
    return found


MANIFEST = {
    "dataset_id": "fixture", "version": "v0", "created": CREATED, "description": "Synthetic test fixture.",
    "generator": {"tool": "tests.search_benchmark_fixture"}, "seeds": {"sample": 0},
    "languages": ("ces", "eng", "deu"), "styles": ("question", "keywords", "entity"),
    "pooling": ({"id": "bm25", "description": "BM25 top 20"},
                {"id": "vector", "description": "Fake vector top 20"}),
    "judges": ({"id": JUDGE, "provenance": {"model": "fake", "prompt_version": "fixture"}},),
    "limitations": ("Synthetic texts; not a corpus sample.",),
}

VECTOR = VectorSpec(id="fake-small", model="fake-small", target_vector="fake_small")
CONFIGURATIONS = ({"configuration_id": "bm25", "mode": "text", "depth": 5},
                  {"configuration_id": "vector", "mode": "vector", "vector": VECTOR, "depth": 5})


def build_dataset(directory: Path) -> Dataset:
    return write_dataset(directory, MANIFEST, corpus(), INTENTS, queries(), qrels())


def build_run(directory: Path, dataset: Dataset) -> Run:
    """BM25 ranks a query's same-language chunks first; the vector ranks the source chunk first.
    One vector search failed; one hit (chunk 5 for a fire query) is not graded."""
    results = []
    for query in dataset.queries.values():
        intent = dataset.intents[query.intent_id]
        same = [c.chunk_id for c in dataset.corpus.values() if c.language == query.language]
        results.append(RunResult(configuration_id="bm25", query_id=query.query_id,
                                 hits=tuple(Hit(chunk_id=i, score=1.0 / (r + 1)) for r, i in enumerate(same)),
                                 search_ms=2.0))
        if query.query_id == "school-council.eng":
            results.append(RunResult(configuration_id="vector", query_id=query.query_id, error="ConnectError",
                                     embed_ms=1.0))
            continue
        relevant = [q.chunk_id for q in dataset.qrels if q.intent_id == intent.intent_id and q.grade]
        rest = [i for i in dataset.corpus if i not in relevant][:5 - len(relevant)]
        results.append(RunResult(configuration_id="vector", query_id=query.query_id,
                                 hits=tuple(Hit(chunk_id=i, score=0.9 - 0.1 * r) for r, i in enumerate(relevant + rest)),
                                 embed_ms=5.0, search_ms=3.0))
    return write_run(directory, {"run_id": "fixture-run", "created": CREATED, "dataset": dataset.ref(),
                                 "configurations": CONFIGURATIONS, "environment": {"weaviate": "fixture"}},
                     results, dataset)


if __name__ == "__main__":
    out = Path(sys.argv[1])
    dataset = build_dataset(out / "dataset")
    build_run(out / "runs" / "fixture-run", dataset)
    print(f"Wrote {out}/dataset and {out}/runs/fixture-run")
