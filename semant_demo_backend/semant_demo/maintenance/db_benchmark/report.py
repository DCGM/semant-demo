"""Markdown rendering of inventory and run results, and the side-by-side comparison of two runs."""
from typing import Any

GIB = 1024 ** 3


def gib(value: int | float | None) -> str:
    return "n/a" if value is None else f"{value / GIB:.1f} GiB"


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _table(header: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(_fmt(c) for c in row) + " |" for row in rows]
    return lines


def environment_lines(env: dict) -> list[str]:
    target = env.get("target", {})
    lines = [f"- Created: {env.get('created_at')}",
             f"- Target: `{target.get('endpoint')}` (Weaviate {target.get('weaviate_version')}), "
             f"chunks collection `{target.get('chunks_collection')}` → `{target.get('chunks_class')}`",
             f"- Tool: db_benchmark v{env.get('tool_version')}, git `{env.get('git_commit')}`"]
    return lines


def inventory_markdown(doc: dict) -> str:
    inv = doc["inventory"]
    out = ["# Weaviate inventory", ""] + environment_lines(doc["environment"]) + [""]
    out += ["## Collections", ""]
    shards = {s["class"]: s for n in inv["nodes"] for s in n["shards"]}
    rows = []
    for name, c in inv["collections"].items():
        s = shards.get(name, {})
        for vname, v in (c["vectors"] or {"-": {}}).items():
            q = v.get("quantizer")
            dims = c.get("vector_dimensions")
            if isinstance(dims, dict):
                dims = dims.get(vname if vname != "(unnamed)" else "default", "none stored")
            rows.append([name, s.get("objectCount"), vname, v.get("type"), dims,
                         ", ".join(f"{k}{'(' + str(x.get('bits')) + 'b)' if x.get('bits') else ''}" for k, x in q.items()) if q else "none",
                         s.get("compressed"), v.get("maxConnections"), v.get("efConstruction"), v.get("ef"),
                         c["inverted"]["usingBlockMaxWAND"], len(c["searchable"]), len(c["references"])])
    out += _table(["collection", "objects", "vector", "index", "dims", "quantizer", "compressed (shard)", "maxConn",
                   "efC", "ef", "BlockMax WAND", "searchable props", "refs"], rows)
    if inv.get("aliases"):
        out += ["", "Aliases: " + ", ".join(f"`{a}` → `{c}`" for a, c in sorted(inv["aliases"].items()))]

    cov = inv.get("vector_coverage")
    if cov:
        out += ["", "## Vector index coverage (self-retrieval)", "",
                f"{cov['sampled']} randomly sampled objects of `{cov['collection']}` (vector `{cov['vector_name']}`, "
                f"seed {cov['seed']}): own object in top-{cov['k']} for **{cov['self_in_top_k']}/{cov['sampled']}** "
                f"({_fmt(cov['self_in_top_k_rate'])}); found by a query restricted to its own id: "
                f"**{cov['found_by_id_filter']}/{cov['sampled']}** ({_fmt(cov['found_by_id_filter_rate'])}). "
                "A healthy index finds nearly all of them."]

    disk = inv.get("disk") or {}
    if disk:
        out += ["", "## Disk", ""]
        fs = disk.get("filesystem")
        if fs:
            out.append(f"- Data filesystem: {gib(fs['total'] - fs['free'])} used of {gib(fs['total'])}, {gib(fs['free'])} free")
        if disk.get("backup_filesystem"):
            b = disk["backup_filesystem"]
            out.append(f"- Backup filesystem: {gib(b['free'])} free of {gib(b['total'])}")
        if disk.get("listed_via"):
            out.append(f"- Files listed via `{disk['listed_via']}` (data directory not fully readable by this user)")
        elif disk.get("unreadable_paths"):
            out.append(f"- **{disk['unreadable_paths']} paths were unreadable; sizes below are incomplete**")
        usage = disk.get("usage")
        if usage:
            out.append(f"- Total data directory: {gib(usage['total_bytes'])}")
            out += ["", *_table(["directory", "size"], [[k, gib(v)] for k, v in list(usage["top_level"].items())[:12]])]
            for coll, comps in usage["components"].items():
                if sum(comps.values()) < GIB:
                    continue
                out += ["", f"### `{coll}` components", ""]
                out += _table(["component", "size"], [[k, gib(v)] for k, v in list(comps.items())[:15]])
                segs = usage["largest_bucket_segments"].get(coll, {})
                for bucket, sizes in segs.items():
                    out.append(f"\n`{bucket}` segments (largest first): " + ", ".join(gib(s) for s in sizes))

    mem = inv.get("memory") or {}
    host, cg = mem.get("host") or {}, mem.get("cgroup")
    out += ["", "## Memory", "",
            f"- Host: {gib(host.get('mem_total'))} total, {gib(host.get('mem_available'))} available, "
            f"page cache {gib(host.get('cached'))}, swap {gib(host.get('swap_total'))}, "
            f"ZFS ARC {gib(host.get('zfs_arc_size'))} (max {gib(host.get('zfs_arc_max'))})"]
    if cg:
        out.append(f"- Container cgroup: current {gib(cg['memory_current'])} (anon {gib(cg['anon'])}, file cache "
                   f"{gib(cg['file'])}), peak since start {gib(cg['memory_peak'])}, limit {gib(cg['memory_max'])}, "
                   f"OOM kills {cg['oom_kill_events']}")
    else:
        out.append(f"- Container cgroup: unavailable ({mem.get('cgroup_unavailable')})")
    if mem.get("container"):
        c = mem["container"]
        out.append(f"- Container: image `{c['image']}`, started {c['started_at']}, restarts {c['restart_count']}, "
                   f"memory limit {gib(c['memory_limit_bytes'])}")

    logs = inv.get("logs")
    if logs and "signals" in logs:
        out += ["", "## Log signals", "",
                f"{logs['lines']} lines from {logs['first']} to {logs['last']}; process starts {logs['startups']}, "
                f"lines mentioning panic {logs['panic_lines']}.", ""]
        out += _table(["count", "level", "action", "message (numbers masked)"],
                      [[e["count"], e["level"], e["action"], e["message"].replace("|", "\\|")] for e in logs["signals"]])
    if inv.get("backups"):
        out += ["", "## Backups (backup-filesystem module)", ""]
        out += _table(["id", "status", "size", "started"], [[b["id"], b["status"], f"{b['size_gib']} GiB", b["started"]]
                                                          for b in inv["backups"]])
    return "\n".join(out) + "\n"


def _resource_cells(res: dict | None) -> list[Any]:
    if not res:
        return ["n/a"] * 4
    return [res.get("cpu_cores_avg"), gib(res.get("anon_max")) if "anon_max" in res else "n/a",
            f"{res['io_read_bytes'] / 2**20:.0f} MiB" if "io_read_bytes" in res else "n/a",
            res.get("host_pressure_io_some_avg10_max")]


def run_markdown(doc: dict) -> str:
    profile = doc["profile"]
    out = ["# Weaviate benchmark run", ""] + environment_lines(doc["environment"])
    out += [f"- Profile: `{profile['name']}` (fingerprint `{doc['profile_fingerprint']}`), seed {profile['seed']}, "
            f"max {profile['max_qps']} req/s, {profile['requests_per_point']} requests or "
            f"{profile['max_seconds_per_point']} s per point, timeout {profile['timeout']} s, "
            f"warm-up {profile['warmup_requests']} requests per scenario",
            "- Inputs: " + ", ".join(f"{k} {v}" for k, v in doc["inputs"].items() if k != "notes")
            + "".join(f"; note: {n}" for n in doc["inputs"].get("notes", [])),
            f"- Resource source: {doc['resource_source']['cgroup'] or doc['resource_source']['unavailable']}",
            f"- Heavy profile opt-in: {doc['allow_heavy']}", ""]
    rows = []
    for s in doc["scenarios"]:
        if s.get("skipped"):
            rows.append([s["name"], s["layer"], "skipped: " + s["skipped"]] + [""] * 12)
            continue
        for p in s["points"]:
            lat = p["latency_ms"]
            rows.append([s["name"], s["layer"], p["concurrency"], p["ok"], p["hit_requests"], p["error_count"], p["timeouts"],
                         lat["p50"], lat["p95"], lat["p99"], lat["max"], p["throughput_rps"],
                         *_resource_cells(p.get("resources"))])
    out += _table(["scenario", "layer", "conc.", "ok", "non-empty", "errors", "timeouts", "p50 ms", "p95 ms", "p99 ms",
                   "max ms", "req/s", "Weaviate CPU cores", "anon max", "disk read", "host IO PSI max"], rows)
    recall = [s for s in doc["scenarios"] if s["kind"] == "self_recall" and not s.get("skipped")]
    for s in recall:
        p = s["points"][0]
        out += ["", f"Self-recall `{s['name']}`: own chunk in top-{s['limit']} for {p['hit_requests']}/{p['ok']} "
                    "sampled chunks."]
    errors = {f"{s['name']}@{p['concurrency']}": p["errors"] for s in doc["scenarios"] for p in s.get("points", [])
              if p["errors"]}
    if errors:
        out += ["", "Errors: " + "; ".join(f"{k}: {v}" for k, v in errors.items())]
    out += ["", "Scenarios: " + "; ".join(f"`{s['name']}` — {s['description']}" for s in doc["scenarios"]
                                          if s.get("description"))]
    return "\n".join(out) + "\n"


def _overlap(a: dict[str, list[str]], b: dict[str, list[str]]) -> tuple[float | None, int]:
    common = [k for k in a if k in b and (a[k] or b[k])]
    if not common:
        return None, 0
    scores = [len(set(a[k]) & set(b[k])) / max(len(a[k]), len(b[k])) for k in common]
    return round(sum(scores) / len(scores), 3), len(common)


def compare_markdown(a: dict, b: dict) -> str:
    """Side by side p50/p95/errors per scenario and concurrency, the differences in setup that
    make the numbers incomparable, and the overlap of result lists for identical queries."""
    out = ["# Benchmark comparison", "", "| | A | B |", "|---|---|---|"]
    ea, eb = a["environment"], b["environment"]
    facts = [
        ("created", ea.get("created_at"), eb.get("created_at")),
        ("endpoint", ea["target"].get("endpoint"), eb["target"].get("endpoint")),
        ("Weaviate", ea["target"].get("weaviate_version"), eb["target"].get("weaviate_version")),
        ("chunks class", ea["target"].get("chunks_class"), eb["target"].get("chunks_class")),
        ("chunk objects", ea["target"].get("chunks_objects"), eb["target"].get("chunks_objects")),
        ("vector index", ea["target"].get("chunks_vector_index"), eb["target"].get("chunks_vector_index")),
        ("profile", f"{a['profile']['name']} ({a['profile_fingerprint']})", f"{b['profile']['name']} ({b['profile_fingerprint']})"),
        ("inputs", a["inputs"].get("sampled_chunks"), b["inputs"].get("sampled_chunks")),
        ("git", ea.get("git_commit"), eb.get("git_commit")),
    ]
    warnings = []
    for label, va, vb in facts:
        out.append(f"| {label} | {_fmt(va)} | {_fmt(vb)} |")
        if label in ("endpoint", "Weaviate", "chunks class", "chunk objects", "vector index", "profile") and va != vb:
            warnings.append(label)
    if warnings:
        out += ["", f"**Setup differs ({', '.join(warnings)}): attribute latency changes with care.**"]
    if a["profile_fingerprint"] != b["profile_fingerprint"] or a["inputs"].get("query_set") != b["inputs"].get("query_set"):
        out += ["", "The query sets differ (profile or sampled inputs): result overlap is only computed for "
                    "identical query fingerprints."]

    out += [""]
    points_b = {(s["name"], p["concurrency"]): (s, p) for s in b["scenarios"] for p in s.get("points", [])}
    rows = []
    for s in a["scenarios"]:
        for p in s.get("points", []):
            other = points_b.get((s["name"], p["concurrency"]))
            if not other:
                rows.append([s["name"], p["concurrency"], p["latency_ms"]["p50"], "—", "", p["latency_ms"]["p95"], "—", "",
                             p["error_count"] + p["timeouts"], "—", "—"])
                continue
            sb, pb = other
            def delta(x, y):
                return f"{(y - x) / x * 100:+.0f}%" if x and y is not None else ""
            overlap, n = _overlap(s.get("results", {}), sb.get("results", {})) if p["concurrency"] == s["points"][0]["concurrency"] else (None, 0)
            rows.append([s["name"], p["concurrency"], p["latency_ms"]["p50"], pb["latency_ms"]["p50"],
                         delta(p["latency_ms"]["p50"], pb["latency_ms"]["p50"]), p["latency_ms"]["p95"],
                         pb["latency_ms"]["p95"], delta(p["latency_ms"]["p95"], pb["latency_ms"]["p95"]),
                         p["error_count"], pb["error_count"],
                         f"{overlap} (n={n})" if overlap is not None else ""])
    out += _table(["scenario", "conc.", "p50 A", "p50 B", "Δp50", "p95 A", "p95 B", "Δp95", "err A", "err B",
                   "result overlap@k"], rows)
    missing = sorted({s["name"] for s in b["scenarios"]} - {s["name"] for s in a["scenarios"]})
    if missing:
        out += ["", "Only in B: " + ", ".join(missing)]
    return "\n".join(out) + "\n"
