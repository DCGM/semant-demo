"""Check, and on explicit request write, the named vectors listed on text chunks (#805).

``Chunks.haveVector`` lists the named vectors computed for a chunk (#560, #590); an embedder
selects the chunks lacking one with ``haveVector contains_none([name])``. This command lists
the given named vector (default ``Qwen3_Embedding_0_6B``) on every chunk that actually stores
it, so the existing corpus is not embedded again:

* a chunk storing the vector whose list lacks the name gets it (``set``; other names already
  listed are kept);
* a chunk without the vector is left as it is and reported (``no_vector``): the embedder will
  select it;
* a chunk listing the name without storing the vector is reported (``listed_without_vector``)
  and left as it is: the embedder would skip it, which needs a decision.

Check (read-only, the default)::

    python -m semant_demo.maintenance.chunk_have_vector --check check.json [--limit N]

Write::

    python -m semant_demo.maintenance.chunk_have_vector --write write.json --confirm-endpoint HOST:PORT \\
        [--vector Qwen3_Embedding_0_6B] [--limit N] [--concurrency 16]

The pass reads every chunk once in id order (pages of 1000: the id, the list and the named
vector, only to learn whether it is stored). Writing first declares ``Chunks.haveVector``
(``text[]``, ``field`` tokenization, filterable, not searchable) if the collection lacks it,
then updates only the chunks to ``set`` (a merge of the single property) and reads each
page's written chunks back. A property-only merge does not re-index the vectors (measured on
production, #805).

The checkpoint (JSON, replaced atomically after each page) holds the endpoint, the resolved
collection, the vector, the mode, the cursor, the counts and the ids whose write failed or did
not read back; running the same command again resumes it, retrying those ids first. A
finished checkpoint is refused. Reported chunks and failed writes get a line in
``CHECKPOINT.manifest.jsonl``.

When the pass is complete and nothing is left to retry, the summary compares the counts the
embedder's predicates find (``contains_any([name])``, ``contains_none([name])`` and all
chunks) with those expected from the pass. Exit code 0 only then, with matching counts, no
``listed_without_vector`` and, for a check, nothing to set; 1 otherwise; 2 when refused.
Run while nothing else writes ``haveVector`` (an embedder) or imports chunks: an update
replaces the whole list.

The Weaviate endpoint comes from ``WEAVIATE_HOST`` / ``WEAVIATE_REST_PORT`` /
``WEAVIATE_GRPC_PORT``.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from weaviate import WeaviateAsyncClient

from semant_demo.adapters.weaviate import have_vector as store
from semant_demo.adapters.weaviate.document_cleanup import resolve_collection
from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.maintenance.chunk_year import _append, _gather, _now, _retrying, _write_json, manifest_path

PAGE_SIZE = 1000
CONCURRENCY = 16
VECTOR = "Qwen3_Embedding_0_6B"
ACTIONS = ("consistent", "set", "no_vector", "listed_without_vector")
REPORTED = ("no_vector", "listed_without_vector")
COUNT_ATTEMPTS = 3
COUNT_PAUSE = 60
"""Seconds between the count comparisons (see ``compare_counts``)."""
QUERY_TIMEOUT = 600
"""Seconds per query: counting 8 million chunks by a filter takes tens of seconds."""


def action(chunk: store.ChunkVectors, vector: str) -> str:
    listed = vector in (chunk.listed or ())
    if chunk.has_vector:
        return "consistent" if listed else "set"
    return "listed_without_vector" if listed else "no_vector"


def target(chunk: store.ChunkVectors, vector: str) -> list[str]:
    return sorted(set(chunk.listed or ()) | {vector})


def _counts() -> dict[str, int]:
    return {"examined": 0, **{a: 0 for a in ACTIONS}, "written": 0}


async def _write(client: WeaviateAsyncClient, chunks: str, vector: str, planned: dict[UUID, list[str]],
                 concurrency: int) -> dict[UUID, str]:
    """Write the planned lists and read them back; the ids not verified, with the reason."""
    errors: dict[UUID, str] = {}

    async def write(chunk_id: UUID) -> None:
        try:
            await _retrying(lambda: store.set_listed(client, chunks, chunk_id, planned[chunk_id]))
        except Exception as e:  # the write may or may not have happened; a retry plans it again
            errors[chunk_id] = f"{type(e).__name__}: {e}"
    await _gather(list(planned), concurrency, write)
    written = [i for i in planned if i not in errors]
    try:
        read_back = await _retrying(lambda: store.read_chunks(client, chunks, vector, written))
    except Exception as e:
        read_back = {}
        errors.update({i: f"read back failed: {type(e).__name__}: {e}" for i in written})
    for chunk_id in written:
        if chunk_id in errors:
            continue
        stored = read_back.get(chunk_id)
        if stored is None or sorted(stored.listed or ()) != planned[chunk_id] or not stored.has_vector:
            errors[chunk_id] = f"read back {stored!r}, expected {planned[chunk_id]!r} with the vector"
    return errors


async def _resolve(client: WeaviateAsyncClient, names: CollectionNames, vector: str):
    chunks = await resolve_collection(client, names.chunks_collection_name)
    if not await client.collections.exists(chunks):
        raise LookupError(f"Collection {chunks} does not exist")
    vectors = await store.vector_names(client, chunks)
    if vector not in vectors:
        raise LookupError(f"{chunks} has no named vector {vector!r} (it has {vectors}); nothing was written")
    prop = await store.declared(client, chunks)
    if prop is not None and prop != store.EXPECTED:
        raise LookupError(f"{chunks}.{store.PROPERTY} is declared as {vars(prop)}, expected "
                          f"{vars(store.EXPECTED)}; it needs a separate, reviewed migration. Nothing was written")
    return chunks, prop


def _load_state(checkpoint: Path, identity: dict[str, Any], progress) -> dict[str, Any]:
    if checkpoint.exists():
        state = json.loads(checkpoint.read_text(encoding="utf-8"))
        differing = sorted(key for key, value in identity.items() if state.get(key) != value)
        if differing:
            raise LookupError(f"The checkpoint {checkpoint} has a different {', '.join(differing)}; "
                              "use a new checkpoint")
        if state["done"] and not state["retry"]:
            raise LookupError(f"The checkpoint {checkpoint} belongs to a finished run; give a new checkpoint "
                              "file name to check or write again")
        progress(f"Resuming {checkpoint}: after {state['after']}, {len(state['retry'])} to retry")
        return state
    state = {**identity, "started": _now(), "after": None, "done": False, "retry": [], "counts": _counts()}
    _write_json(checkpoint, state)
    return state


def _progress(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


async def compare_counts(client: WeaviateAsyncClient, chunks: str, vector: str, counts: dict[str, int],
                         write: bool, attempts: int = COUNT_ATTEMPTS) -> dict[str, Any]:
    """What the embedder's predicates find against what the pass expects (after its writes),
    counted again after ``COUNT_PAUSE`` seconds on a mismatch: right after 8.3 M merges on
    production, ``contains_none`` counted more chunks than the collection held (8 759 358 of
    8 280 272) and 0 a few minutes later, as expected (#805)."""
    for attempt in range(1, attempts + 1):
        result = await _compare_once(client, chunks, vector, counts, write)
        if result["match"] or attempt == attempts:
            return result | {"attempts": attempt}
        await asyncio.sleep(COUNT_PAUSE)
    raise AssertionError("unreachable")


async def _compare_once(client: WeaviateAsyncClient, chunks: str, vector: str, counts: dict[str, int],
                        write: bool) -> dict[str, Any]:
    listed = counts["consistent"] + counts["listed_without_vector"] + (counts["set"] if write else 0)
    result: dict[str, Any] = {"expected_listed": listed, "expected_not_listed": counts["examined"] - listed,
                              "expected_all": counts["examined"]}
    try:
        result["listed"] = await _retrying(lambda: store.count(client, chunks, vector, listed=True))
        result["not_listed"] = await _retrying(lambda: store.count(client, chunks, vector, listed=False))
        result["all"] = await _retrying(lambda: store.count(client, chunks))
    except Exception as e:
        return result | {"match": False, "error": f"{type(e).__name__}: {e}"}
    result["match"] = (result["listed"], result["not_listed"], result["all"]) == (
        result["expected_listed"], result["expected_not_listed"], result["expected_all"])
    return result


async def run(client: WeaviateAsyncClient, names: CollectionNames, *, checkpoint: Path, endpoint: str,
              write: bool, vector: str = VECTOR, limit: int | None = None, concurrency: int = CONCURRENCY,
              progress=_progress) -> dict[str, Any]:
    """One pass over the chunks (see the module docstring); returns the summary. Raises
    ``LookupError`` before writing if the collection or vector is missing, the property is
    declared otherwise or the checkpoint belongs to another run."""
    chunks, prop = await _resolve(client, names, vector)
    identity = {"endpoint": endpoint, "chunks": chunks, "vector": vector, "mode": "write" if write else "check"}
    state = _load_state(checkpoint, identity, progress)
    if write and prop is None:
        await store.add_property(client, chunks)
        state["property_added"] = _now()
        progress(f"Declared {chunks}.{store.PROPERTY} ({vars(store.EXPECTED)})")
        prop = await store.declared(client, chunks)
    is_declared = prop is not None
    manifest = manifest_path(checkpoint)
    counts = state["counts"]
    started, examined = time.monotonic(), 0

    def save() -> None:
        state["updated"] = _now()
        _write_json(checkpoint, state)

    pending = [UUID(i) for i in state["retry"]]
    for start in range(0, len(pending), PAGE_SIZE):
        ids = pending[start:start + PAGE_SIZE]
        stored = await _retrying(lambda: store.read_chunks(client, chunks, vector, ids, is_declared))
        planned = {c.id: target(c, vector) for c in stored.values() if action(c, vector) == "set"}
        errors = await _write(client, chunks, vector, planned, concurrency) if planned else {}
        counts["written"] += len(planned) - len(errors)
        retried = {str(i) for i in ids}
        _append(manifest, [{"id": str(i), "status": "failed", "reason": r} for i, r in errors.items()]
                + [{"id": i, "status": "verified_on_retry" if UUID(i) in stored else "absent_on_retry"}
                   for i in sorted(retried - {str(e) for e in errors})])
        state["retry"] = sorted((set(state["retry"]) - retried) | {str(e) for e in errors})
        save()

    while not state["done"] and (limit is None or examined < limit):
        size = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - examined)
        after = UUID(state["after"]) if state["after"] else None
        page = await _retrying(lambda: store.read_chunk_page(client, chunks, vector, after, size, is_declared))
        planned: dict[UUID, list[str]] = {}
        lines: list[dict[str, Any]] = []
        for chunk in page:
            act = action(chunk, vector)
            counts[act] += 1
            if act in REPORTED:
                lines.append({"id": str(chunk.id), "status": act, "listed": chunk.listed})
            if act == "set" and write:
                planned[chunk.id] = target(chunk, vector)
        errors = await _write(client, chunks, vector, planned, concurrency) if planned else {}
        counts["written"] += len(planned) - len(errors)
        lines += [{"id": str(i), "status": "failed", "reason": r} for i, r in errors.items()]
        _append(manifest, lines)
        counts["examined"] += len(page)
        examined += len(page)
        state["retry"] = sorted(set(state["retry"]) | {str(e) for e in errors})
        if page:
            state["after"] = str(page[-1].id)
        state["done"] = len(page) < size
        save()
        seconds = max(time.monotonic() - started, 1e-3)
        progress(f"examined {counts['examined']} " + " ".join(f"{a} {counts[a]}" for a in ACTIONS)
                 + f" written {counts['written']} to retry {len(state['retry'])} after {state['after']}"
                 f" ({examined / seconds:.0f}/s this run)")

    if state["done"] and not state["retry"] and is_declared:
        state["search_counts"] = await compare_counts(client, chunks, vector, counts, write)
    state["finished"] = _now()
    save()
    keys = ("endpoint", "chunks", "vector", "mode", "after", "done", "counts")
    return {key: state[key] for key in keys} | {
        "to_retry": len(state["retry"]), "property": prop and vars(prop),
        "property_added": state.get("property_added"), "search_counts": state.get("search_counts"),
        "checkpoint": str(checkpoint), "manifest": str(manifest)}


def exit_code(result: dict[str, Any]) -> int:
    if not result["done"] or result["to_retry"] or not (result["search_counts"] or {}).get("match"):
        return 1
    counts = result["counts"]
    if counts["listed_without_vector"] or (result["mode"] == "check" and counts["set"]):
        return 1
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", type=Path, metavar="CHECKPOINT", help="compare the lists with the stored vectors")
    mode.add_argument("--write", type=Path, metavar="CHECKPOINT",
                      help="declare Chunks.haveVector if missing and list the stored vector; resumes")
    p.add_argument("--confirm-endpoint", metavar="HOST:PORT", help="with --write: the configured Weaviate endpoint")
    p.add_argument("--vector", default=VECTOR, help=f"the named vector (default {VECTOR})")
    p.add_argument("--limit", type=int, help="at most this many chunks in this run")
    p.add_argument("--concurrency", type=int, default=CONCURRENCY, help=f"parallel writes (default {CONCURRENCY})")
    return p


async def _main(argv: list[str]) -> int:
    from semant_demo.adapters.weaviate.client import connect_weaviate
    from semant_demo.config import Config

    args = _parser().parse_args(argv)
    config = Config()
    endpoint = f"{config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}"
    if args.write and args.confirm_endpoint != endpoint:
        print(f"Refusing to write: configured endpoint {endpoint}, --confirm-endpoint {args.confirm_endpoint}",
              file=sys.stderr)
        return 2
    print(f"Weaviate endpoint: {endpoint}", file=sys.stderr)
    client = await connect_weaviate(config, query_timeout=QUERY_TIMEOUT)
    try:
        result = await run(client, config.collectionNames, checkpoint=args.write or args.check, endpoint=endpoint,
                           write=bool(args.write), vector=args.vector, limit=args.limit,
                           concurrency=args.concurrency)
        print(json.dumps(result, indent=2))
        return exit_code(result)
    except LookupError as e:
        print(e, file=sys.stderr)
        return 2
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
