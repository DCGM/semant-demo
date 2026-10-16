"""Read-only inventory of a Weaviate deployment: version, collections, index settings,
counts, vector coverage, disk use per component, memory, backups and log signals."""
import collections
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import httpx
from weaviate import WeaviateAsyncClient

from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.maintenance.db_benchmark import resources
from semant_demo.maintenance.db_benchmark.profile import Profile, QueryInputs
from semant_demo.maintenance.db_benchmark.workload import id_filtered_self_hit, sample_inputs

QUANTIZERS = ("pq", "bq", "sq", "rq")
CONTAINER_DATA_PATH = "/var/lib/weaviate"


def _vector_index(config: dict | None) -> dict[str, Any] | None:
    if not config:
        return None
    quantizers = {q: {k: v for k, v in config[q].items() if k in ("bits", "rescoreLimit", "segments", "centroids")}
                  for q in QUANTIZERS if (config.get(q) or {}).get("enabled")}
    keys = ("distance", "ef", "efConstruction", "maxConnections", "vectorCacheMaxObjects", "filterStrategy",
            "flatSearchCutoff", "dynamicEfMin", "dynamicEfMax", "dynamicEfFactor", "skip")
    summary = {k: config.get(k) for k in keys if k in config}
    summary["quantizer"] = quantizers or None
    if (config.get("multivector") or {}).get("enabled"):
        summary["multivector"] = True
    return summary


def collection_summary(cls: dict) -> dict[str, Any]:
    vectors = {}
    if cls.get("vectorIndexConfig") is not None and cls.get("vectorIndexType"):
        vectors["(unnamed)"] = {"type": cls.get("vectorIndexType"), **(_vector_index(cls["vectorIndexConfig"]) or {})}
    for name, vc in (cls.get("vectorConfig") or {}).items():
        vectors[name] = {"type": vc.get("vectorIndexType"), **(_vector_index(vc.get("vectorIndexConfig")) or {})}
    props = cls.get("properties", [])
    refs = [p["name"] for p in props if p["dataType"][0][0].isupper()]
    inverted = cls.get("invertedIndexConfig", {})
    return {
        "vectors": vectors,
        "inverted": {"bm25": inverted.get("bm25"), "usingBlockMaxWAND": inverted.get("usingBlockMaxWAND", False),
                     "stopwords": (inverted.get("stopwords") or {}).get("preset"),
                     "indexTimestamps": inverted.get("indexTimestamps", False),
                     "indexNullState": inverted.get("indexNullState", False),
                     "indexPropertyLength": inverted.get("indexPropertyLength", False)},
        "properties": len(props),
        "searchable": sorted(p["name"] for p in props if p.get("indexSearchable")),
        "filterable": len([p for p in props if p.get("indexFilterable")]),
        "range_filters": sorted(p["name"] for p in props if p.get("indexRangeFilters")),
        "references": sorted(refs),
        "sharding": {k: (cls.get("shardingConfig") or {}).get(k) for k in ("desiredCount", "actualCount")},
        "replication_factor": (cls.get("replicationConfig") or {}).get("factor"),
        "multi_tenancy": (cls.get("multiTenancyConfig") or {}).get("enabled", False),
    }


def scan_files(entries: list[tuple[int, str]]) -> dict[str, Any]:
    """Disk use by collection directory, shard component and LSM bucket from (bytes, relative path)."""
    total = 0
    by_top: dict[str, int] = collections.Counter()
    components: dict[str, dict[str, int]] = collections.defaultdict(collections.Counter)
    segments: dict[str, dict[str, list[int]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    for size, rel in entries:
        total += size
        parts = rel.split("/")
        by_top[parts[0]] += size
        if len(parts) >= 3 and "." not in parts[0]:
            component = parts[2]
            if component == "lsm" and len(parts) >= 4:
                component = f"lsm/{parts[3]}"
                if parts[-1].endswith(".db") and len(parts) == 5:
                    segments[parts[0]][parts[3]].append(size)
            components[parts[0]][component] += size
    return {
        "total_bytes": total,
        "top_level": dict(sorted(by_top.items(), key=lambda kv: -kv[1])),
        "components": {c: dict(sorted(v.items(), key=lambda kv: -kv[1])) for c, v in components.items()},
        "largest_bucket_segments": {c: {b: sorted(s, reverse=True)[:12] for b, s in v.items()
                                        if b in ("objects",) or b.startswith("vectors")}
                                    for c, v in segments.items()},
    }


def walk_data_dir(path: str) -> tuple[list[tuple[int, str]], list[str]]:
    entries, unreadable = [], []
    for root, dirs, files in os.walk(path, onerror=lambda e: unreadable.append(os.path.relpath(e.filename, path))):
        for name in files:
            full = os.path.join(root, name)
            try:
                entries.append((os.lstat(full).st_size, os.path.relpath(full, path)))
            except OSError:
                unreadable.append(os.path.relpath(full, path))
    return entries, unreadable


def container_files(container: str, path: str = CONTAINER_DATA_PATH) -> list[tuple[int, str]]:
    """File sizes under the data path, listed by ``find`` inside the container (read-only).

    ``-xdev`` keeps mounts below the data path out (e.g. a backup directory mounted at
    ``/var/lib/weaviate/backups``), as ``--data-dir`` on the host does.
    """
    out = subprocess.run(["docker", "exec", container, "find", path, "-xdev", "-type", "f", "-exec", "stat", "-c", "%s %n",
                          "{}", "+"],
                         capture_output=True, text=True, timeout=600, check=True).stdout
    return parse_files_list(out, path)


def parse_files_list(text: str, path: str = CONTAINER_DATA_PATH) -> list[tuple[int, str]]:
    """(bytes, path relative to ``path``) from '<bytes> <path>' lines."""
    entries = []
    for line in text.splitlines():
        size, _, name = line.partition(" ")
        if size.isdigit():
            entries.append((int(size), os.path.relpath(name, path)))
    return entries


LOG_NUMBER = re.compile(r"\d+(\.\d+)?")


def container_log(container: str, since: str | None) -> str:
    cmd = ["docker", "logs", container] + (["--since", since] if since else [])
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return proc.stdout + proc.stderr


def log_signals(text: str) -> dict[str, Any]:
    """Counts of warning/error/fatal log entries by action and message prefix (numbers masked,
    no payload fields), startups and lines mentioning a panic in a Weaviate (JSON) log."""
    lines = text.splitlines()
    counts: collections.Counter = collections.Counter()
    first = last = None
    panics = startups = 0
    for line in lines:
        if "panic" in line.lower():
            panics += 1
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        first = first or entry.get("time")
        last = entry.get("time") or last
        if str(entry.get("msg", "")).startswith("loading local db"):
            startups += 1
        level = entry.get("level")
        if level in ("warning", "error", "fatal", "panic"):
            msg = LOG_NUMBER.sub("N", str(entry.get("msg", "")))[:90]
            counts[(level, entry.get("action", "-"), msg)] += 1
    return {"lines": len(lines), "first": first, "last": last, "panic_lines": panics, "startups": startups,
            "signals": [{"count": n, "level": level, "action": action, "message": msg}
                        for (level, action, msg), n in counts.most_common(30)]}


async def vector_coverage(client: WeaviateAsyncClient, names: CollectionNames, sample: int, k: int,
                          seed: int, target_vector: str | None) -> dict[str, Any]:
    """Self-retrieval of randomly sampled chunks: near_vector(own vector) in the top ``k``, and a
    query restricted to the chunk's own id. A healthy index finds (nearly) all of them."""
    profile = Profile(name="coverage", seed=seed, scenarios=[], queries=QueryInputs(sample_objects=sample))
    inputs = await sample_inputs(client, names, profile, target_vector)
    chunks = [c for c in inputs.chunks if c.vector is not None]
    collection = client.collections.get(names.chunks_collection_name)
    top_k = top1 = by_id = 0
    for chunk in chunks:
        result = await collection.query.near_vector(near_vector=chunk.vector, target_vector=inputs.vector_name,
                                                    limit=k, return_properties=[])
        ids = [o.uuid for o in result.objects]
        top_k += chunk.id in ids
        top1 += bool(ids) and ids[0] == chunk.id
        by_id += await id_filtered_self_hit(client, names, chunk, inputs.vector_name)
    n = len(chunks)
    return {"collection": names.chunks_collection_name, "vector_name": inputs.vector_name, "sampled": n,
            "k": k, "seed": seed, "self_in_top_k": top_k, "self_top1": top1, "found_by_id_filter": by_id,
            "self_in_top_k_rate": round(top_k / n, 4) if n else None,
            "found_by_id_filter_rate": round(by_id / n, 4) if n else None}


async def collect(client: WeaviateAsyncClient, base_url: str, names: CollectionNames, *, coverage_sample: int,
                  coverage_k: int, seed: int, target_vector: str | None, data_dir: str | None,
                  container: str | None, container_files_scan: bool, files_list: str | None,
                  cgroup: tuple, logs_since: str | None, log_file: str | None,
                  backup_dir: str | None) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=base_url, timeout=60) as http:
        meta = (await http.get("/v1/meta")).json()
        schema = (await http.get("/v1/schema")).json()
        nodes = (await http.get("/v1/nodes", params={"output": "verbose"})).json()
        aliases_response = await http.get("/v1/aliases")
        aliases = aliases_response.json().get("aliases", []) if aliases_response.status_code == 200 else None
        backups_response = await http.get("/v1/backups/filesystem")
        backups = backups_response.json() if backups_response.status_code == 200 else None

    result: dict[str, Any] = {
        "weaviate": {"version": meta.get("version"), "modules": sorted((meta.get("modules") or {}).keys())},
        "nodes": [{"name": n.get("name"), "status": n.get("status"), "version": n.get("version"),
                   "git_hash": n.get("gitHash"), "stats": n.get("stats"),
                   "shards": [{k: s.get(k) for k in ("class", "name", "objectCount", "vectorIndexingStatus",
                                                     "vectorQueueLength", "compressed", "loaded")}
                              for s in (n.get("shards") or [])]}
                  for n in nodes.get("nodes", [])],
        "aliases": {a["alias"]: a["class"] for a in aliases} if aliases is not None else None,
        "collections": {c["class"]: collection_summary(c) for c in schema.get("classes", [])},
        # Backup ids are not recorded (they may name operations or hosts); the start time identifies a backup.
        "backups": [{"status": b.get("status"), "size_gib": round(b.get("size") or 0, 1),
                     "started": (b.get("startedAt") or "")[:19], "collections": len(b.get("classes") or [])}
                    for b in backups] if isinstance(backups, list) else None,
    }

    # Vector dimensions per collection and vector name (one object each).
    for name, summary in result["collections"].items():
        if not summary["vectors"]:
            continue
        try:
            response = await client.collections.get(name).query.fetch_objects(limit=1, include_vector=True,
                                                                               return_properties=[])
            vector = response.objects[0].vector if response.objects else {}
            summary["vector_dimensions"] = {k: len(v) for k, v in vector.items()} if isinstance(vector, dict) else None
        except Exception as e:
            summary["vector_dimensions"] = f"unavailable: {type(e).__name__}"

    if coverage_sample > 0:
        result["vector_coverage"] = await vector_coverage(client, names, coverage_sample, coverage_k, seed, target_vector)

    disk: dict[str, Any] = {}
    entries: list[tuple[int, str]] = []
    if data_dir:
        disk["filesystem"] = resources.disk_usage(data_dir)
        entries, unreadable = walk_data_dir(data_dir)
        disk["unreadable_paths"] = len(unreadable)
        disk["unreadable_examples"] = unreadable[:5]
    if files_list:
        entries = parse_files_list(Path(files_list).read_text())
        disk["listed_via"] = "a saved file list"
    elif container and container_files_scan:
        entries = container_files(container)
        disk["listed_via"] = "docker exec find in the container"
    if data_dir or files_list or container_files_scan:
        disk["usage"] = scan_files(entries)
    if backup_dir:
        disk["backup_filesystem"] = resources.disk_usage(backup_dir)
    result["disk"] = disk or None

    cgroup, reason = cgroup
    result["memory"] = {"host": resources.host_snapshot(), "cgroup": resources.cgroup_snapshot(cgroup),
                        "cgroup_unavailable": reason if cgroup is None else None,
                        "container": resources.container_config(container) if container else None}
    if log_file:
        result["logs"] = log_signals(Path(log_file).read_text(errors="replace"))
    elif container and logs_since != "none":
        try:
            result["logs"] = log_signals(container_log(container, logs_since))
        except (OSError, subprocess.SubprocessError) as e:
            result["logs"] = {"unavailable": type(e).__name__}
    return result
