"""The database benchmark tool (#374) against the seeded test store: every scenario kind runs,
a healthy vector index finds each sampled chunk by its own vector, and nothing is written."""
import json

import pytest

from semant_demo.maintenance.db_benchmark import cli

pytestmark = pytest.mark.integration


async def _counts(client) -> dict[str, int]:
    names = [c for c in await client.collections.list_all(simple=True)]
    return {n: (await client.collections.get(n).aggregate.over_all(total_count=True)).total_count for n in names}


def _target(store_endpoint) -> list[str]:
    return ["--host", store_endpoint.host, "--rest-port", str(store_endpoint.rest_port),
            "--grpc-port", str(store_endpoint.grpc_port)]


async def test_smoke_run_and_inventory_are_read_only(seeded_store, store_endpoint, corpus, tmp_path):
    before = await _counts(seeded_store)

    run_args = cli.parser().parse_args(["run", "--profile", "smoke", "--out", str(tmp_path / "run"),
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

    compare_args = cli.parser().parse_args(["compare", str(tmp_path / "run.json"), str(tmp_path / "run.json"),
                                            "--out", str(tmp_path / "cmp")])
    assert cli.cmd_compare(compare_args) == 0
    assert "1.0 (n=" in (tmp_path / "cmp.md").read_text()
