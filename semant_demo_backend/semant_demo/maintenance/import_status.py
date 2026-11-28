"""Report, read-only, how far every stage of an import has reached the imported documents (#884, #560).

After appending chunks (``chunk_ingest``) and running the stages of ``docs/DATA_MAINTENANCE.md``
(*Afterwards*), an exit code 0 of each stage does not prove that every imported record was
enriched. This command reads only the listed documents and their chunks and reports, per
stage, how many are complete, with the ids of those that are not::

    python -m semant_demo.maintenance.import_status --report REPORT.json --document-ids CHECKPOINT.documents.txt \\
        [--vector-name Qwen3_Embedding_0_6B] [--coverage-sample 100] [--coverage-k 10] [--seed 884] \\
        [--titles-included-restricted] [--classifier-skipped-restricted]

``--document-ids`` is the document list that ``chunk_ingest --write`` writes (one UUID per
line, ``#`` starts a comment). It writes nothing to the store and needs no
``--confirm-endpoint``; the summary is printed and saved to ``REPORT.json`` (a new file).

Stages (``stages`` in the report):

* ``chunks`` (documents): the document has chunks;
* ``metadata`` (documents): ``metadata_sync`` resolved it: ``public`` is a bool
  (``unresolved`` otherwise) and ``library`` is set. Documents without a title or a year are
  counted under ``documents_without`` (the source may have none), not as incomplete;
* ``year`` (chunks): ``yearIssued`` equals the document's year, absent when the document has
  none (``chunk_year``);
* ``visibility`` (chunks): ``documentPublic`` is ``true`` exactly when the document's
  ``public`` is ``true`` (``chunk_document_public``);
* ``titles`` (chunks): a non-empty ``title`` (``chunk_titles``);
* ``vectors`` (chunks): ``haveVector`` lists ``--vector-name`` (the embedder);
* ``classification`` (chunks): ``classification_provenance`` other than ``UNPROCESSED`` (the
  classifier);
* ``summaries`` (documents): the chunk-value summaries equal a recomputation from the
  document's chunks, as ``chunk_summaries`` compares them, and have been computed.

Expected gaps are counted apart (``expected_gaps``), not as incomplete. The chunks of a
document that is not public (``public`` false or absent, #785) follow the stage's defaults:

* untitled ones are a gap (``deferred_restricted_document``): ``chunk_titles`` defers them;
  ``--titles-included-restricted`` (it ran with ``--include-restricted-documents``) counts
  them as incomplete;
* ``UNPROCESSED`` ones are incomplete: the classifier with a local model, as configured in the
  repository, classifies them; ``--classifier-skipped-restricted`` (an API model without
  ``include_restricted_documents``) counts them as a gap (``skipped_restricted_document``).

Chunks without ``classification_provenance`` were stored before the property existed
(``chunk_ingest`` sets ``UNPROCESSED`` on every chunk it inserts), e.g. the earlier chunks of a
document the import appends to; they are a gap (``stored_before_status``).

Vector index (``index``): for up to ``--coverage-sample`` chunks sampled (``--seed``) among
those that list the vector, the checks of ``db_benchmark inventory --coverage-sample``, on the
imported chunks only:

* a vector query with the chunk's own stored vector finds it in the top ``--coverage-k``. A
  chunk missing there is queried again with the top ``RETRY_FACTOR`` x ``K`` (``retried``): a
  chunk with duplicate text shares its vector with other chunks, and the graph search is
  approximate. Only a miss there too counts, as a self-retrieval miss (``not_in_top_k``): a
  sign, not proof, that the chunk is missing from the graph that search walks, since a correctly
  indexed chunk among many identical vectors can miss too;
* a vector query restricted to the chunk's id finds it. Weaviate answers so selective a filter
  by a flat (brute-force) search over the matching objects (``flatSearchCutoff``), so this
  shows only that the vector is stored and readable, not that it is in the graph.

A miss right after the embedder may be a vector still queued for indexing (asynchronous
indexing): run the report again later.

Exit code 0 when every stage is complete for the listed documents (expected gaps aside) and the
index finds every sampled chunk; 1 when something is incomplete or missed; 2 when refused: the
report exists, the document list is missing, empty or not UUIDs, a listed document does not
exist, a collection, a property the stages write or the named vector is missing, or
``--coverage-sample`` is below 0 or ``--coverage-k`` below 1. Run it while
nothing writes the imported documents.

The Weaviate endpoint comes from ``WEAVIATE_HOST`` / ``WEAVIATE_REST_PORT`` /
``WEAVIATE_GRPC_PORT``.
"""
import argparse
import asyncio
import json
import random
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from uuid import UUID

from weaviate import WeaviateAsyncClient

from semant_demo.adapters.weaviate import import_status as store
from semant_demo.adapters.weaviate.chunk_summaries import expected_properties
from semant_demo.adapters.weaviate.classification_provenance import PROPERTY as PROVENANCE, UNPROCESSED
from semant_demo.adapters.weaviate.document_cleanup import resolve_collection
from semant_demo.adapters.weaviate.have_vector import PROPERTY as HAVE_VECTOR
from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.maintenance.chunk_summaries import DIMENSIONS, Summaries
from semant_demo.maintenance.chunk_year import canonical_year

VECTOR_NAME = "Qwen3_Embedding_0_6B"
"""The named vector the embedder's ``config.qwen.yaml`` fills."""
COVERAGE_SAMPLE = 100
COVERAGE_K = 10
SEED = 884
RETRY_FACTOR = 10
"""A chunk missing from the top ``K`` is queried again with the top ``RETRY_FACTOR * K``."""
ID_LIMIT = 100
"""Incomplete ids listed per stage (and missed ids of the index check); the counts are complete."""
DOCUMENT_BATCH = 100
"""Documents read per query of their metadata."""
CONCURRENCY = 8
"""Documents whose chunks are read in parallel."""
QUERY_TIMEOUT = 600

YEAR, PUBLIC_FLAG, TITLE = "yearIssued", "documentPublic", "title"
CHUNK_PROPERTIES = {YEAR: "chunk_year --write", PUBLIC_FLAG: "chunk_document_public --write",
                    TITLE: "the Chunks schema", HAVE_VECTOR: "chunk_have_vector --write",
                    PROVENANCE: "classification_provenance_schema --apply"}
"""The chunk properties the stages write, with the step that declares each."""
DOCUMENT_STAGES = ("chunks", "metadata", "summaries")
CHUNK_STAGES = ("year", "visibility", "titles", "vectors", "classification")
STAGES = ("chunks", "metadata", "year", "visibility", "titles", "vectors", "classification", "summaries")


class Refused(LookupError):
    """The report cannot be made; nothing was read beyond the schema."""


def _progress(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def read_document_ids(path: Path) -> list[UUID]:
    """The ids of the document list (one UUID per line, ``#`` starts a comment), in order, once."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        raise Refused(f"Cannot read the document list {path}: {type(e).__name__}") from e
    ids = []
    for number, line in enumerate(lines, 1):
        text = line.split("#", 1)[0].strip()
        if not text:
            continue
        try:
            ids.append(UUID(text))
        except ValueError:
            raise Refused(f"{path}:{number} is not a document UUID: {text!r}") from None
    if not ids:
        raise Refused(f"The document list {path} lists no documents")
    return list(dict.fromkeys(ids))


class Stage:
    """Complete, incomplete (with the first ``ID_LIMIT`` ids) and expected-gap counts of one stage."""

    def __init__(self, unit: str):
        self.unit = unit
        self.complete = 0
        self.incomplete: Counter[str] = Counter()
        self.expected: Counter[str] = Counter()
        self.ids: list[dict[str, str]] = []

    def done(self) -> None:
        self.complete += 1

    def missing(self, object_id: UUID, reason: str) -> None:
        self.incomplete[reason] += 1
        if len(self.ids) < ID_LIMIT:
            self.ids.append({"id": str(object_id), "reason": reason})

    def gap(self, reason: str) -> None:
        self.expected[reason] += 1

    def summary(self) -> dict[str, Any]:
        return {"unit": self.unit, "complete": self.complete, "incomplete": sum(self.incomplete.values()),
                "expected_gaps": sum(self.expected.values()), "incomplete_reasons": dict(self.incomplete),
                "expected_gap_reasons": dict(self.expected), "incomplete_ids": self.ids,
                "incomplete_ids_truncated": sum(self.incomplete.values()) > len(self.ids)}


def check_metadata(document: store.ImportedDocument, stage: Stage, without: Counter[str]) -> None:
    public, library = document.properties["public"], document.properties["library"]
    if not isinstance(public, bool):
        stage.missing(document.id, "unresolved")
    elif not (isinstance(library, str) and library.strip()):
        stage.missing(document.id, "no_library")
    else:
        stage.done()
    for name in ("title", YEAR):
        if document.properties[name] in (None, ""):
            without[name] += 1


def check_chunk(chunk: store.ImportedChunk, document: store.ImportedDocument, vector_name: str,
                stages: dict[str, Stage], *, titles_include_restricted: bool = False,
                classifier_includes_restricted: bool = True) -> None:
    """Record the chunk in each chunk stage. The two options say whether ``chunk_titles`` and the
    classifier processed the chunks of documents that are not public (see the module docstring)."""
    public = document.properties["public"] is True
    try:
        year = canonical_year(document.properties[YEAR])
    except ValueError:
        stages["year"].missing(chunk.id, "invalid_document_year")
    else:
        stored = chunk.properties[YEAR]
        if stored == year and (stored is None) == (year is None):
            stages["year"].done()
        else:
            stages["year"].missing(chunk.id, "absent" if stored is None else "extra" if year is None else "differs")

    flag = chunk.properties[PUBLIC_FLAG]
    if flag is public:
        stages["visibility"].done()
    else:
        stages["visibility"].missing(chunk.id, "absent" if flag is None else "differs")

    title = chunk.properties[TITLE]
    if isinstance(title, str) and title.strip():
        stages["titles"].done()
    elif public or titles_include_restricted:
        stages["titles"].missing(chunk.id, "untitled")
    else:
        stages["titles"].gap("deferred_restricted_document")

    if vector_name in (chunk.properties[HAVE_VECTOR] or ()):
        stages["vectors"].done()
    else:
        stages["vectors"].missing(chunk.id, "not_listed")

    provenance = chunk.properties[PROVENANCE]
    if provenance is None:
        stages["classification"].gap("stored_before_status")
    elif provenance != UNPROCESSED:
        stages["classification"].done()
    elif not public and not classifier_includes_restricted:
        stages["classification"].gap("skipped_restricted_document")
    else:
        stages["classification"].missing(chunk.id, "unprocessed")


def check_summaries(document: store.ImportedDocument, chunks: Sequence[store.ImportedChunk],
                    chunk_dimensions: Sequence[str], stage: Stage) -> None:
    summaries = Summaries(DIMENSIONS)
    for chunk in chunks:
        summaries.add(document.id, {d: store.text_values(chunk.properties[d]) for d in chunk_dimensions})
    expected = summaries.pop(document.id)
    if document.computed_at is None:
        stage.missing(document.id, "never_computed")
    elif document.summaries != expected:
        stage.missing(document.id, "differs")
    else:
        stage.done()


async def _resolve(client: WeaviateAsyncClient, names: CollectionNames, vector_name: str) -> tuple[str, str, list[str]]:
    """The chunks and documents collections and the chunk dimensions declared; refuses what the
    stages cannot have written."""
    chunks = await resolve_collection(client, names.chunks_collection_name)
    documents = await resolve_collection(client, names.document_collection_name)
    for name in (chunks, documents):
        if not await client.collections.exists(name):
            raise Refused(f"Collection {name} does not exist")
    declared = await store.declared_properties(client, chunks)
    missing = [f"{p} ({step})" for p, step in CHUNK_PROPERTIES.items() if p not in declared]
    if missing:
        raise Refused(f"{chunks} does not declare {', '.join(missing)}")
    summary_properties = set(expected_properties(DIMENSIONS))
    missing_summaries = sorted(summary_properties - await store.declared_properties(client, documents))
    if missing_summaries:
        raise Refused(f"{documents} does not declare {', '.join(missing_summaries)} "
                      "(chunk_summary_schema --apply)")
    if vector_name not in await store.vector_names(client, chunks):
        raise Refused(f"{chunks} has no named vector {vector_name}")
    return chunks, documents, [d for d in DIMENSIONS if d in declared]


async def _read_documents(client: WeaviateAsyncClient, documents: str,
                          ids: list[UUID]) -> dict[UUID, store.ImportedDocument]:
    found: dict[UUID, store.ImportedDocument] = {}
    for start in range(0, len(ids), DOCUMENT_BATCH):
        found.update(await store.read_documents(client, documents, ids[start:start + DOCUMENT_BATCH], DIMENSIONS))
    unknown = [str(i) for i in ids if i not in found]
    if unknown:
        shown = ", ".join(unknown[:ID_LIMIT])
        raise Refused(f"{len(unknown)} listed documents do not exist in {documents}: {shown}"
                      + (" ..." if len(unknown) > ID_LIMIT else ""))
    return found


async def check_index(client: WeaviateAsyncClient, chunks: str, candidates: list[UUID], vector_name: str,
                      sample: int, k: int, seed: int) -> dict[str, Any]:
    """Self-retrieval of up to ``sample`` chunks drawn from ``candidates``."""
    chosen = random.Random(seed).sample(sorted(candidates), min(sample, len(candidates)))
    vectors = await store.read_vectors(client, chunks, chosen, vector_name)
    retry_k = k * RETRY_FACTOR
    top_k = in_retry = by_id = 0
    retried: list[str] = []
    missed: list[dict[str, str]] = []
    for chunk_id in chosen:
        vector = vectors.get(chunk_id)
        if vector is None:
            missed.append({"id": str(chunk_id), "reason": "no_stored_vector"})
            continue
        found = await store.self_in_top_k(client, chunks, chunk_id, vector, vector_name, k)
        top_k += found
        if not found:
            retried.append(str(chunk_id))
            found = await store.self_in_top_k(client, chunks, chunk_id, vector, vector_name, retry_k)
            in_retry += found
        by_filter = await store.found_by_id_filter(client, chunks, chunk_id, vector, vector_name)
        by_id += by_filter
        if not found:
            missed.append({"id": str(chunk_id), "reason": "not_in_top_k"})
        elif not by_filter:
            missed.append({"id": str(chunk_id), "reason": "not_found_by_id_filter"})
    return {"vector_name": vector_name, "candidates": len(candidates), "sampled": len(chosen), "k": k,
            "retry_k": retry_k, "seed": seed, "self_in_top_k": top_k, "retried": len(retried),
            "self_in_retry_k": in_retry, "found_by_id_filter": by_id, "missed": len(missed),
            "retried_ids": retried[:ID_LIMIT], "missed_ids": missed[:ID_LIMIT]}


async def run(client: WeaviateAsyncClient, names: CollectionNames, *, report: Path, document_ids: list[UUID],
              endpoint: str, vector_name: str = VECTOR_NAME, coverage_sample: int = COVERAGE_SAMPLE,
              coverage_k: int = COVERAGE_K, seed: int = SEED, titles_include_restricted: bool = False,
              classifier_includes_restricted: bool = True, concurrency: int = CONCURRENCY,
              progress: Callable[[str], None] = _progress) -> dict[str, Any]:
    """The report (see the module docstring), also saved to ``report``. Raises ``Refused``
    before reading any chunk when it cannot be made."""
    if coverage_sample < 0 or coverage_k < 1:
        raise Refused(f"--coverage-sample must be 0 or more and --coverage-k 1 or more "
                      f"(given {coverage_sample} and {coverage_k})")
    if report.exists():
        raise Refused(f"The report {report} exists; give a new report file name")
    chunks, documents_collection, chunk_dimensions = await _resolve(client, names, vector_name)
    started = time.monotonic()
    documents = await _read_documents(client, documents_collection, document_ids)

    stages = {name: Stage("documents" if name in DOCUMENT_STAGES else "chunks") for name in STAGES}
    without: Counter[str] = Counter()
    with_vector: list[UUID] = []
    properties = [*CHUNK_PROPERTIES, *chunk_dimensions]
    semaphore = asyncio.Semaphore(concurrency)
    examined = 0

    async def read(document_id: UUID) -> list[store.ImportedChunk]:
        async with semaphore:
            return await store.read_document_chunks(client, chunks, document_id, properties)

    for start in range(0, len(document_ids), DOCUMENT_BATCH):
        part = document_ids[start:start + DOCUMENT_BATCH]
        for document_id, document_chunks in zip(part, await asyncio.gather(*(read(i) for i in part))):
            document = documents[document_id]
            if document_chunks:
                stages["chunks"].done()
            else:
                stages["chunks"].missing(document_id, "no_chunks")
            check_metadata(document, stages["metadata"], without)
            for chunk in document_chunks:
                check_chunk(chunk, document, vector_name, stages, titles_include_restricted=titles_include_restricted,
                            classifier_includes_restricted=classifier_includes_restricted)
                if vector_name in (chunk.properties[HAVE_VECTOR] or ()):
                    with_vector.append(chunk.id)
            check_summaries(document, document_chunks, chunk_dimensions, stages["summaries"])
            examined += len(document_chunks)
        progress(f"documents {min(start + DOCUMENT_BATCH, len(document_ids))}/{len(document_ids)}, "
                 f"chunks {examined}")

    index = await check_index(client, chunks, with_vector, vector_name, coverage_sample, coverage_k, seed)
    result = {
        "endpoint": endpoint, "chunks": chunks, "documents": documents_collection,
        "options": {"titles_include_restricted": titles_include_restricted,
                    "classifier_includes_restricted": classifier_includes_restricted},
        "documents_listed": len(document_ids), "chunks_examined": examined,
        "stages": {name: stage.summary() for name, stage in stages.items()},
        "documents_without": {name: without[name] for name in ("title", YEAR)},
        "chunk_dimensions_not_declared": [d for d in DIMENSIONS if d not in chunk_dimensions],
        "index": index, "seconds": round(time.monotonic() - started, 1), "report": str(report)}
    result["complete"] = exit_code(result) == 0
    report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def exit_code(result: dict[str, Any]) -> int:
    """0 when no stage has incomplete documents or chunks and the index missed no sampled chunk."""
    incomplete = any(stage["incomplete"] for stage in result["stages"].values())
    return 1 if incomplete or result["index"]["missed"] else 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--report", type=Path, required=True, metavar="REPORT", help="the report to write (a new file)")
    p.add_argument("--document-ids", type=Path, required=True, metavar="FILE",
                   help="the imported documents (one UUID per line, e.g. CHECKPOINT.documents.txt)")
    p.add_argument("--vector-name", default=VECTOR_NAME, help=f"the named vector (default {VECTOR_NAME})")
    p.add_argument("--coverage-sample", type=int, default=COVERAGE_SAMPLE,
                   help=f"chunks for the index check (default {COVERAGE_SAMPLE}; 0: skip)")
    p.add_argument("--coverage-k", type=int, default=COVERAGE_K, help=f"top K of the index check (default {COVERAGE_K})")
    p.add_argument("--seed", type=int, default=SEED, help=f"seed of the sample (default {SEED})")
    p.add_argument("--titles-included-restricted", action="store_true",
                   help="chunk_titles ran with --include-restricted-documents: untitled chunks of documents that "
                        "are not public are incomplete, not a gap")
    p.add_argument("--classifier-skipped-restricted", action="store_true",
                   help="the classifier skipped the chunks of documents that are not public (an API model without "
                        "include_restricted_documents): their UNPROCESSED chunks are a gap, not incomplete")
    return p


async def _main(argv: list[str]) -> int:
    from semant_demo.adapters.weaviate.client import connect_weaviate
    from semant_demo.config import Config

    args = _parser().parse_args(argv)
    try:
        document_ids = read_document_ids(args.document_ids)
    except Refused as e:
        print(e, file=sys.stderr)
        return 2
    config = Config()
    endpoint = f"{config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}"
    print(f"Weaviate endpoint: {endpoint}", file=sys.stderr)
    client = await connect_weaviate(config, query_timeout=QUERY_TIMEOUT)
    try:
        result = await run(client, config.collectionNames, report=args.report, document_ids=document_ids,
                           endpoint=endpoint, vector_name=args.vector_name, coverage_sample=args.coverage_sample,
                           coverage_k=args.coverage_k, seed=args.seed,
                           titles_include_restricted=args.titles_included_restricted,
                           classifier_includes_restricted=not args.classifier_skipped_restricted)
        print(json.dumps(result, indent=2))
        return exit_code(result)
    except Refused as e:
        print(e, file=sys.stderr)
        return 2
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
