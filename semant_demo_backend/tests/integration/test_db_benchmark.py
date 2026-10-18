"""The database benchmark tool (#374) against the seeded test store: every scenario kind runs,
filtered searches use filter values that match chunks, a healthy vector index finds each
sampled chunk by its own vector, and nothing is written."""
import json

import pytest

from semant_demo.maintenance.db_benchmark import cli

pytestmark = pytest.mark.integration


async def _counts(client) -> dict[str, int]:
    """Objects per collection; per tenant for multi-tenant collections (the annotations)."""
    counts = {}
    for name, config in (await client.collections.list_all(simple=False)).items():
        collection = client.collections.get(name)
        if config.multi_tenancy_config.enabled:
            for tenant in await collection.tenants.get():
                counts[f"{name}/{tenant}"] = (
                    await collection.with_tenant(tenant).aggregate.over_all(total_count=True)).total_count
        else:
            counts[name] = (await collection.aggregate.over_all(total_count=True)).total_count
    return counts


def _target(store_endpoint) -> list[str]:
    return ["--host", store_endpoint.host, "--rest-port", str(store_endpoint.rest_port),
            "--grpc-port", str(store_endpoint.grpc_port)]


async def test_smoke_run_and_inventory_are_read_only(seeded_store, store_endpoint, corpus, tmp_path):
    before = await _counts(seeded_store)

    key = ["--id-key-file", str(tmp_path / "key")]
    run_args = cli.parser().parse_args(["run", "--profile", "smoke", "--out", str(tmp_path / "run"), *key,
                                        *_target(store_endpoint)])
    assert await cli.cmd_run(run_args) == 0
    inv_args = cli.parser().parse_args(["inventory", "--coverage-sample", "5", "--logs-since", "none",
                                        "--out", str(tmp_path / "inv"), *_target(store_endpoint)])
    assert await cli.cmd_inventory(inv_args) == 0

    assert await _counts(seeded_store) == before

    run = json.loads((tmp_path / "run.json").read_text())
    by_name = {s["name"]: s for s in run["scenarios"]}
    assert run["inputs"]["vector_dimensions"] > 0
    assert run["inputs"]["sampled_chunks"] == min(8, len(corpus.chunks))
    for name in ("bm25", "vector", "hybrid", "hybrid_year", "hybrid_user_collection", "hybrid_direct",
                 "chunk_context", "document_view", "corpus_overview", "mixed", "self_recall"):
        points = by_name[name]["points"]
        assert points and all(p["error_count"] == 0 for p in points), name
    # Only tags / collections that hold chunks are sampled, so the filtered searches find results.
    assert run["inputs"]["tags"] > 0 and run["inputs"]["user_collections"] > 0
    for name in ("hybrid_tag", "hybrid_user_collection"):
        assert all(p["hit_requests"] > 0 for p in by_name[name]["points"]), name
    # Every level runs the same number of requests (the same inputs by default).
    assert len({p["requests"] for p in by_name["hybrid"]["points"]}) == 1
    assert run["id_hashing"]["key_id"] == cli.id_hasher(str(tmp_path / "key")).key_id
    recall = by_name["self_recall"]["points"][0]
    assert recall["hit_requests"] == recall["ok"] == run["inputs"]["with_vector"]
    serialized = (tmp_path / "run.json").read_text()
    assert not any(str(chunk["id"]) in serialized for chunk in corpus.chunks.values())
    assert not any(chunk["text"][:30] in serialized for chunk in corpus.chunks.values())

    inv = json.loads((tmp_path / "inv.json").read_text())["inventory"]
    coverage = inv["vector_coverage"]
    assert coverage["self_in_top_k"] == coverage["found_by_id_filter"] == coverage["sampled"] > 0
    assert "Chunks" in inv["collections"]
    assert (tmp_path / "run.md").read_text().startswith("# Weaviate benchmark run")
    summary = json.loads((tmp_path / "run.summary.json").read_text())
    assert summary["kind"] == "run_summary" and not any("results" in s for s in summary["scenarios"])

    # Disjoint level inputs: each level runs the next inputs of the sample.
    fresh_args = cli.parser().parse_args(["run", "--profile", "smoke", "--scenarios", "hybrid", "--level-inputs",
                                          "disjoint", "--out", str(tmp_path / "fresh"), *key, *_target(store_endpoint)])
    assert await cli.cmd_run(fresh_args) == 0
    fresh = json.loads((tmp_path / "fresh.json").read_text())
    assert "next inputs" in fresh["input_reuse"] and fresh["scenarios"][0]["points"][0]["error_count"] == 0
    assert await _counts(seeded_store) == before

    compare_args = cli.parser().parse_args(["compare", str(tmp_path / "run.json"), str(tmp_path / "run.json"),
                                            "--out", str(tmp_path / "cmp")])
    assert cli.cmd_compare(compare_args) == 0
    assert "1.0 (n=" in (tmp_path / "cmp.md").read_text()
