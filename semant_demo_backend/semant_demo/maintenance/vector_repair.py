"""Temporary, best-effort in-place repair of the damaged chunk vector index (#375).

No re-embedding or schema changes. A small probe of *missing* index entries must
succeed before a bounded resumable pass can be started. See docs/VECTOR_REPAIR.md.
This is intentionally NOT a general index-migration framework.
"""
import argparse
import asyncio
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from weaviate.classes.query import Filter

from semant_demo.adapters.weaviate.client import connect_weaviate
from semant_demo.adapters.weaviate.document_cleanup import resolve_collection
from semant_demo.config import Config

VECTOR = "default"
PAGE = 20


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(temp, path)


def _vector(obj, name: str):
    if isinstance(obj.vector, dict):
        return obj.vector.get(name)
    return obj.vector if name == "default" else None


async def _self_hit(collection, obj, name: str) -> bool:
    vector = _vector(obj, name)
    if vector is None:
        return False
    result = await collection.query.near_vector(
        near_vector=vector, target_vector=name, filters=Filter.by_id().equal(obj.uuid),
        limit=1, return_properties=[])
    return any(hit.uuid == obj.uuid for hit in result.objects)


async def _missing_samples(collection, name: str, count: int, seed: int):
    """Find missing entries using the same random-UUID cursor idea as the audit."""
    rng = random.Random(seed)
    selected, seen = [], set()
    for _ in range(count * 40):
        if len(selected) >= count:
            break
        page = await collection.query.fetch_objects(
            limit=1, after=UUID(int=rng.getrandbits(128)),
            include_vector=True, return_properties=[])
        if not page.objects:
            continue
        obj = page.objects[0]
        if obj.uuid in seen or _vector(obj, name) is None:
            continue
        seen.add(obj.uuid)
        if not await _self_hit(collection, obj, name):
            selected.append(obj)
    return selected


async def _probe(collection, target: dict, args) -> int:
    samples = await _missing_samples(collection, args.vector, args.sample, args.seed)
    if not samples:
        print("No missing vectors sampled; no repair authorized.", file=sys.stderr)
        return 2
    print(f"Found {len(samples)} missing index entries; writing their existing vectors.")
    failures = 0
    for obj in samples:
        try:
            await collection.data.update(uuid=obj.uuid, vector={args.vector: _vector(obj, args.vector)})
        except Exception as exc:
            failures += 1
            print(f"Probe update failed: {type(exc).__name__}: {exc}", file=sys.stderr)

    deadline = time.monotonic() + args.wait_seconds
    repaired = set()
    while time.monotonic() < deadline:
        for obj in samples:
            if obj.uuid not in repaired and await _self_hit(collection, obj, args.vector):
                repaired.add(obj.uuid)
        if len(repaired) == len(samples):
            break
        await asyncio.sleep(2)
    success = bool(repaired) and not failures
    result = {**target, "type": "vector_repair_probe", "at": datetime.now(timezone.utc).isoformat(),
              "sampled_missing": len(samples), "repaired": len(repaired),
              "update_failures": failures, "success": success}
    _save(Path(args.report), result)
    print(f"Probe: {len(repaired)}/{len(samples)} previously missing vectors now retrievable; "
          f"failures={failures}. Report: {args.report}")
    if not success:
        print("Do not start bulk updates: identical-vector updates did not demonstrate a fix.",
              file=sys.stderr)
    return 0 if success else 1


async def _write_page(collection, objects, vector_name: str, concurrency: int) -> None:
    semaphore = asyncio.Semaphore(concurrency)

    async def update(obj):
        vector = _vector(obj, vector_name)
        if vector is None:
            return
        async with semaphore:
            await collection.data.update(uuid=obj.uuid, vector={vector_name: vector})
    # Stop on any error. If some writes landed, the checkpoint is NOT advanced;
    # restarting safely replays this small page.
    await asyncio.gather(*(update(obj) for obj in objects))


async def _run(collection, target: dict, args) -> int:
    probe = json.loads(Path(args.probe_report).read_text())
    if probe.get("type") != "vector_repair_probe" or not probe.get("success"):
        raise ValueError("The matching probe has not demonstrated a successful repair")
    if any(probe.get(k) != target[k] for k in target):
        raise ValueError("The probe was performed against a different endpoint, collection or vector")

    path = Path(args.checkpoint)
    if path.exists():
        state = json.loads(path.read_text())
        if any(state.get(k) != target[k] for k in target) or state.get("type") != "vector_repair_run":
            raise ValueError("Checkpoint belongs to a different target")
    else:
        state = {**target, "type": "vector_repair_run", "after": None,
                 "scanned": 0, "rewritten": 0, "skipped": 0, "complete": False}
        _save(path, state)

    remaining = args.limit
    if state["complete"]:
        print("Checkpoint already reached the end of the collection")
        return 0
    while remaining:
        limit = min(args.page_size, remaining)
        after = UUID(state["after"]) if state["after"] else None
        response = await collection.query.fetch_objects(
            limit=limit, after=after, include_vector=True, return_properties=[])
        objects = response.objects
        if not objects:
            state["complete"] = True
            _save(path, state)
            break
        try:
            await _write_page(collection, objects, args.vector, args.concurrency)
        except Exception as exc:
            print(f"Write stopped at previous checkpoint: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
            return 1
        # Cursor advances only after every write of this page was accepted.
        state["after"] = str(objects[-1].uuid)
        state["scanned"] += len(objects)
        state["rewritten"] += sum(_vector(obj, args.vector) is not None for obj in objects)
        state["skipped"] += sum(_vector(obj, args.vector) is None for obj in objects)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save(path, state)
        remaining -= len(objects)
        print(f"Scanned {state['scanned']}, rewritten {state['rewritten']}, "
              f"skipped {state['skipped']}; cursor {state['after']}", flush=True)
        await asyncio.sleep(args.pause)
        if len(objects) < limit:
            state["complete"] = True
            _save(path, state)
            break
    print(f"Stopped at checkpoint {path}. Existing changes are not rolled back; "
          "asynchronous indexing may continue after the command exits.")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default=None)
    p.add_argument("--rest-port", type=int, default=None)
    p.add_argument("--grpc-port", type=int, default=None)
    p.add_argument("--collection", default="Chunks", help="existing collection or alias")
    p.add_argument("--vector", default=VECTOR)
    p.add_argument("--confirm-endpoint", required=True, help="exact HOST:REST_PORT")
    p.add_argument("--execute", action="store_true", help="required for all writes")
    sub = p.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("probe", help="test a few missing vectors before any bulk pass")
    probe.add_argument("--report", required=True)
    probe.add_argument("--sample", type=int, default=5)
    probe.add_argument("--seed", type=int, default=375)
    probe.add_argument("--wait-seconds", type=int, default=120)
    run = sub.add_parser("run", help="resume up to --limit objects from checkpoint")
    run.add_argument("--probe-report", required=True)
    run.add_argument("--checkpoint", required=True)
    run.add_argument("--limit", type=int, default=200)
    run.add_argument("--page-size", type=int, default=PAGE)
    run.add_argument("--concurrency", type=int, default=2)
    run.add_argument("--pause", type=float, default=1.0)
    return p


async def main_async(args) -> int:
    env = dict(os.environ)
    for key, value in (("WEAVIATE_HOST", args.host), ("WEAVIATE_REST_PORT", args.rest_port),
                       ("WEAVIATE_GRPC_PORT", args.grpc_port)):
        if value is not None:
            env[key] = str(value)
    config = Config(environ=env)
    endpoint = f"{config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}"
    if not args.execute or args.confirm_endpoint != endpoint:
        print(f"Refused: need --execute --confirm-endpoint {endpoint}", file=sys.stderr)
        return 2
    if args.command == "probe":
        if not 1 <= args.sample <= 20 or not 1 <= args.wait_seconds <= 600:
            raise ValueError("probe sample must be 1..20 and wait time 1..600 seconds")
    elif not (1 <= args.limit <= 10000 and 1 <= args.page_size <= 100
              and 1 <= args.concurrency <= 8 and 0 <= args.pause <= 60):
        raise ValueError("run limits: 1..10000 objects, 1..100/page, 1..8 workers, 0..60 s pause")
    client = await connect_weaviate(config, query_timeout=120)
    try:
        physical = await resolve_collection(client, args.collection)
        if not await client.collections.exists(physical):
            raise LookupError(f"Collection {physical!r} does not exist")
        target = {"endpoint": endpoint, "collection": physical, "vector": args.vector}
        collection = client.collections.get(physical)
        if args.command == "probe":
            return await _probe(collection, target, args)
        return await _run(collection, target, args)
    finally:
        await client.close()


def main() -> int:
    args = parser().parse_args()
    try:
        return asyncio.run(main_async(args))
    except (OSError, ValueError, LookupError) as exc:
        print(f"Refused/stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
