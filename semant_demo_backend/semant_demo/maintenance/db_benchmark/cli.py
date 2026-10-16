"""Command line: ``inventory``, ``run``, ``compare``, ``report`` and ``sanitize`` (see the package docstring)."""
import argparse
import asyncio
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from semant_demo.adapters.weaviate.client import connect_weaviate
from semant_demo.adapters.weaviate.document_cleanup import resolve_collection
from semant_demo.config import Config
from semant_demo.maintenance.db_benchmark import inventory, report, resources
from semant_demo.maintenance.db_benchmark.profile import SAFE, apply_overrides, available_profiles, load_profile
from semant_demo.maintenance.db_benchmark.runner import run_point
from semant_demo.maintenance.db_benchmark.workload import (
    LAYER, IdHasher, Workload, collection_names, sample_inputs)

TOOL_VERSION = 2
"""2: keyed id hashes, the same inputs at every concurrency level, matching tag/collection filters."""
REFUSED = 2
DEFAULT_KEY_FILE = Path("~/.config/semant-demo/db-benchmark-id-key")


def id_hasher(path: str | None) -> IdHasher:
    """The id hash key from ``path`` (default ``DEFAULT_KEY_FILE``), created with a random key if missing."""
    file = Path(path).expanduser() if path else DEFAULT_KEY_FILE.expanduser()
    if not file.exists():
        file.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32) + "\n")
        print(f"Created id hash key {file} (keep it to compare later runs with this one)")
    return IdHasher(file.read_text().strip().encode())


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5,
                              cwd=Path(__file__).parent).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _config(args) -> Config:
    env = dict(os.environ)
    for key, value in (("WEAVIATE_HOST", args.host), ("WEAVIATE_REST_PORT", args.rest_port),
                       ("WEAVIATE_GRPC_PORT", args.grpc_port)):
        if value is not None:
            env[key] = str(value)
    return Config(environ=env)


def _cgroup(args) -> tuple[Path | None, str | None]:
    if args.cgroup:
        path = Path(args.cgroup)
        return (path, None) if (path / "memory.current").exists() else (None, "--cgroup has no readable memory.current")
    if args.container:
        return resources.container_cgroup(args.container)
    return None, "neither --container nor --cgroup given"


def _index_label(v: dict) -> str:
    quantizer = ",".join(q + str(x.get("bits") or "") for q, x in (v.get("quantizer") or {}).items()) or "none"
    return f"{v.get('type')} maxConn={v.get('maxConnections')} efC={v.get('efConstruction')} ef={v.get('ef')} quantizer={quantizer}"


async def _environment(client, config: Config, names) -> dict[str, Any]:
    meta = await client.get_meta()
    chunks_class = await resolve_collection(client, names.chunks_collection_name)
    chunks = client.collections.get(names.chunks_collection_name)
    total = (await chunks.aggregate.over_all(total_count=True)).total_count
    try:
        async with httpx.AsyncClient(timeout=30) as http:
            schema = (await http.get(f"http://{config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}/v1/schema/{chunks_class}")).json()
        vector_index = "; ".join(f"{name}: {_index_label(v)}"
                                 for name, v in inventory.collection_summary(schema)["vectors"].items())
    except Exception as e:  # the summary is informative only
        vector_index = f"unavailable: {type(e).__name__}"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool_version": TOOL_VERSION, "git_commit": _git_commit(),
        "target": {"endpoint": f"{config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}",
                   "weaviate_version": meta.get("version"), "chunks_collection": names.chunks_collection_name,
                   "chunks_class": chunks_class, "chunks_objects": total, "chunks_vector_index": vector_index},
    }


def _write(doc: dict, markdown: str, out: str) -> None:
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(f"{out}.json").write_text(json.dumps(doc, indent=1, default=str) + "\n")
    Path(f"{out}.md").write_text(markdown)
    written = [f"{out}.json", f"{out}.md"]
    if doc.get("kind") == "run":
        Path(f"{out}.summary.json").write_text(json.dumps(report.run_summary(doc), indent=1, default=str) + "\n")
        written.append(f"{out}.summary.json")
    print("Wrote " + ", ".join(written))


def _default_out(kind: str) -> str:
    return f"db-benchmark-{kind}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"


async def cmd_inventory(args) -> int:
    config = _config(args)
    names = config.collectionNames
    client = await connect_weaviate(config, query_timeout=120)
    try:
        doc = {"kind": "inventory", "environment": await _environment(client, config, names)}
        doc["inventory"] = await inventory.collect(
            client, f"http://{config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}", names,
            coverage_sample=args.coverage_sample, coverage_k=args.coverage_k, seed=args.seed,
            target_vector=args.target_vector, data_dir=args.data_dir, container=args.container,
            container_files_scan=args.container_files, files_list=args.files_list, cgroup=_cgroup(args),
            logs_since=args.logs_since, log_file=args.log_file, backup_dir=args.backup_dir)
    finally:
        await client.close()
    _write(doc, report.inventory_markdown(doc), args.out or _default_out("inventory"))
    return 0


def _profile(args):
    """The profile with the command-line overrides; ValueError when it or an override is invalid."""
    profile = load_profile(args.profile)
    try:
        levels = [int(c) for c in args.concurrency.split(",")] if args.concurrency else None
    except ValueError:
        raise ValueError(f"--concurrency {args.concurrency!r}: expected comma-separated integers") from None
    profile = apply_overrides(profile, {
        "concurrency": levels, "requests_per_point": args.requests, "max_seconds_per_point": args.max_seconds,
        "timeout": args.timeout, "max_qps": args.max_qps, "seed": args.seed})
    if args.scenarios is not None:
        wanted = {n for n in args.scenarios.split(",") if n}
        unknown = wanted - {s.name for s in profile.scenarios}
        if not wanted or unknown:
            raise ValueError(f"--scenarios: unknown or no scenario names {sorted(unknown)}; profile has "
                             + ", ".join(s.name for s in profile.scenarios))
        keep = [s for s in profile.scenarios if s.name in wanted]
        needed = {n for s in keep if s.kind == "mixed" for n in s.of}
        profile = apply_overrides(profile, {"scenarios": [s.model_dump() for s in profile.scenarios
                                                          if s.name in wanted | needed]})
    return profile


async def cmd_run(args) -> int:
    try:
        profile = _profile(args)
    except (ValueError, OSError) as e:  # pydantic's ValidationError is a ValueError
        print(f"Refused: invalid profile or override: {e}", file=sys.stderr)
        return REFUSED
    violations = profile.violations()
    config = _config(args)
    print(f"Target {config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}, profile {profile.name} "
          f"({len(profile.scenarios)} scenarios, concurrency {profile.concurrency}, max {profile.max_qps} req/s)")
    if violations and not args.allow_heavy:
        print("Refused: the profile exceeds the production-safe limits (" + "; ".join(violations) +
              "). Pass --allow-heavy only for a staging instance or a snapshot.", file=sys.stderr)
        return REFUSED

    names = collection_names(profile, config.collectionNames)
    hasher = id_hasher(args.id_key_file)
    cgroup, reason = _cgroup(args)
    client = await connect_weaviate(config, query_timeout=profile.timeout + 5)
    sampler = resources.ResourceSampler(cgroup).start()
    try:
        environment = await _environment(client, config, names)
        t0 = time.monotonic()
        inputs = await sample_inputs(client, names, profile, args.target_vector)
        input_summary = inputs.summary()
        input_summary["sampling_seconds"] = round(time.monotonic() - t0, 2)
        input_summary["query_set"] = hasher(sorted(str(c.id) for c in inputs.chunks)
                                            + sorted(map(str, inputs.tags + inputs.user_collections)))
        workload = Workload(client, names, profile, inputs)
        scenarios = []
        sampler.window()
        for scenario in profile.scenarios:
            entry: dict[str, Any] = {"name": scenario.name, "kind": scenario.kind, "layer": LAYER[scenario.kind],
                                     "description": scenario.description, "limit": scenario.limit,
                                     "mode": scenario.mode, "filter": scenario.filter, "points": []}
            scenarios.append(entry)
            skip = workload.skip_reason(scenario)
            if skip:
                entry["skipped"] = skip
                print(f"  {scenario.name}: skipped ({skip})")
                continue
            request = workload.request(scenario)
            levels = scenario.concurrency or profile.concurrency
            if scenario.kind == "self_recall":
                levels, count = [1], workload.input_count(scenario)
            else:
                count = profile.requests_per_point
                if profile.warmup_requests:
                    # Warm-up on the last inputs (negative indices wrap), which the points use only
                    # when they need more requests than there are other inputs.
                    await run_point(request, 1, profile.warmup_requests, profile.max_seconds_per_point,
                                    profile.timeout, profile.max_qps, start_index=-profile.warmup_requests)
            for i, level in enumerate(levels):
                # Every level runs the same inputs (indices 0..count-1), so levels differ only in
                # concurrency; levels after the first re-run inputs the store has just served.
                sampler.window()
                point = await run_point(request, level, count, profile.max_seconds_per_point, profile.timeout,
                                        profile.max_qps, start_index=0, keep_results=i == 0)
                summary = point.summary()
                summary["resources"] = sampler.window()
                entry["points"].append(summary)
                if i == 0:
                    entry["results"] = {hasher(workload.fingerprint(scenario, idx)): [hasher.rekey(h) for h in ids]
                                        for idx, ids in point.results.items()}
                lat = summary["latency_ms"]
                print(f"  {scenario.name} c={level}: {point.ok} ok, {summary['error_count']} errors, "
                      f"p50 {lat['p50']} ms, p95 {lat['p95']} ms")
                await asyncio.sleep(profile.pause_between_points)
    finally:
        sampler.stop()
        await client.close()

    doc = {"kind": "run", "environment": environment, "profile": profile.model_dump(mode="json"),
           "profile_fingerprint": profile.fingerprint(), "allow_heavy": bool(args.allow_heavy),
           "safety_limits": SAFE.model_dump(), "inputs": input_summary, "id_hashing": hasher.describe(),
           "input_reuse": "every concurrency level runs the same inputs; levels after the first re-run them",
           "resource_source": resources.source_label(cgroup, reason), "scenarios": scenarios}
    _write(doc, report.run_markdown(doc), args.out or _default_out("run"))
    return 0


def cmd_compare(args) -> int:
    a, b = (json.loads(Path(p).read_text()) for p in (args.a, args.b))
    if a.get("kind") != "run" or b.get("kind") != "run":
        print("compare needs two run results", file=sys.stderr)
        return REFUSED
    markdown = report.compare_markdown(a, b)
    out = args.out or _default_out("compare")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(f"{out}.md").write_text(markdown)
    print(f"Wrote {out}.md")
    return 0


def cmd_report(args) -> int:
    doc = json.loads(Path(args.result).read_text())
    markdown = report.inventory_markdown(doc) if doc.get("kind") == "inventory" else report.run_markdown(doc)
    _write(doc, markdown, str(Path(args.result).with_suffix("")))
    return 0


def cmd_sanitize(args) -> int:
    """Writes a copy of a result fit for publication (see ``report.sanitize``)."""
    doc = json.loads(Path(args.result).read_text())
    if doc.get("kind") not in ("run", "inventory"):
        print("sanitize needs a run or inventory result", file=sys.stderr)
        return REFUSED
    clean = report.sanitize(doc, id_hasher(args.id_key_file))
    markdown = report.inventory_markdown(clean) if clean["kind"] == "inventory" else report.run_markdown(clean)
    _write(clean, markdown, args.out)
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m semant_demo.maintenance.db_benchmark",
                                description="Read-only Weaviate inventory and bounded query benchmark.")
    sub = p.add_subparsers(dest="command", required=True)

    def target(sp):
        sp.add_argument("--host", help="Weaviate host (default: WEAVIATE_HOST or localhost)")
        sp.add_argument("--rest-port", type=int, help="default: WEAVIATE_REST_PORT or 8080")
        sp.add_argument("--grpc-port", type=int, help="default: WEAVIATE_GRPC_PORT or 50051")
        sp.add_argument("--container", help="Docker container of Weaviate: cgroup CPU/memory/IO and limits")
        sp.add_argument("--cgroup", help="cgroup v2 directory of Weaviate, when --container cannot be resolved "
                                         "(e.g. the tool itself runs in a container with the host cgroup mounted)")
        sp.add_argument("--target-vector", help="named vector to query (default: the first by name; "
                                                "an explicitly named vector that does not exist is an error)")
        sp.add_argument("--out", help="output path prefix (default: db-benchmark-<kind>-<time>)")

    def key_file(sp):
        sp.add_argument("--id-key-file", help=f"secret key for the id hashes in results (default: {DEFAULT_KEY_FILE}, "
                                              "created if missing); compare only runs made with the same key")

    inv = sub.add_parser("inventory", help="configuration, counts, coverage, disk, memory, logs")
    target(inv)
    inv.add_argument("--coverage-sample", type=int, default=100, help="chunks for the self-retrieval check (0: skip)")
    inv.add_argument("--coverage-k", type=int, default=10)
    inv.add_argument("--seed", type=int, default=374)
    inv.add_argument("--data-dir", help="host path of the Weaviate data directory (sizes per component)")
    inv.add_argument("--container-files", action="store_true",
                     help="list data files with 'docker exec <container> find' when --data-dir is not readable")
    inv.add_argument("--files-list", help="'<bytes> <path>' lines of the data directory's files, e.g. from "
                                          "'docker exec C find /var/lib/weaviate -xdev -type f -exec stat -c \\'%%s %%n\\' {} +'")
    inv.add_argument("--backup-dir", help="host path of the backup directory (free space)")
    inv.add_argument("--log-file", help="saved Weaviate log (e.g. 'docker logs C > weaviate.log') instead of docker logs")
    inv.add_argument("--logs-since", default=None,
                     help="docker logs --since value for log signals ('none': skip; default: whole log)")

    run = sub.add_parser("run", help="bounded read-only benchmark of a workload profile")
    target(run)
    run.add_argument("--profile", default="baseline", help=f"profile name ({', '.join(available_profiles())}) or YAML path")
    run.add_argument("--scenarios", help="comma-separated subset of the profile's scenarios")
    run.add_argument("--concurrency", help="comma-separated levels, e.g. 1,5,10")
    run.add_argument("--requests", type=int, help="requests per scenario and level")
    run.add_argument("--max-seconds", type=float, help="time cap per scenario and level")
    run.add_argument("--timeout", type=float, help="per-request timeout (s)")
    run.add_argument("--max-qps", type=float, help="request starts per second across all workers")
    run.add_argument("--seed", type=int)
    run.add_argument("--allow-heavy", action="store_true",
                     help="permit limits above the production-safe defaults (staging/snapshot only)")
    key_file(run)

    cmp = sub.add_parser("compare", help="side-by-side Markdown of two run results")
    cmp.add_argument("a")
    cmp.add_argument("b")
    cmp.add_argument("--out")

    rep = sub.add_parser("report", help="re-render the Markdown (and a run's summary) of a saved result")
    rep.add_argument("result")

    san = sub.add_parser("sanitize", help="copy of a result for publication: keyed id hashes (also converts "
                                          "version 1 results), no host paths or backup ids")
    san.add_argument("result")
    san.add_argument("--out", required=True, help="output path prefix")
    key_file(san)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "inventory":
        return asyncio.run(cmd_inventory(args))
    if args.command == "run":
        return asyncio.run(cmd_run(args))
    if args.command == "compare":
        return cmd_compare(args)
    if args.command == "sanitize":
        return cmd_sanitize(args)
    return cmd_report(args)
