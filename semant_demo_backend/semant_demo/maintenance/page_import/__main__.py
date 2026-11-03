"""Import page scans, layout files and chunk-start anchors for the existing corpus (#542).

From ``semant_demo_backend/``; the Weaviate endpoint comes from ``WEAVIATE_HOST`` /
``WEAVIATE_REST_PORT`` / ``WEAVIATE_GRPC_PORT``, the asset store from ``--assets-dir`` (default
``PAGE_ASSETS_DIR``)::

    # 1. files only; reads the chunks read-only
    python -m semant_demo.maintenance.page_import assets --page-order pages.jsonl --report assets.json \\
        [DOCUMENT_ID ... | --document-ids ids.txt] [--assets-dir DIR] \\
        [--line-confidence 0.6] [--min-chunk-chars 768] [--max-chunk-chars 1152] [--max-edit-ratio 0.05]

    # 2. compare (read-only), then write the anchors
    python -m semant_demo.maintenance.page_import anchors --check check.json [ids] [--assets-dir DIR]
    python -m semant_demo.maintenance.page_import anchors --write write.json --confirm-endpoint HOST:PORT \\
        [ids] [--assets-dir DIR] [--concurrency 8]

``assets`` takes the documents of a ``page_order`` export (#571; ``--check-start-pages``
recommended), in its order or that of the given ids. Per document it reads the PAGE XML zips and
scans the export names and the stored chunks, runs the #540 converter against the stored chunks
and writes, per page, the layout file (when it differs), the original scan (when the stored copy
is missing or of another size; the source must be a JPEG) and a thumbnail, then the manifest
and the anchor plan (``anchors.jsonl``). Missing or corrupt sources are reported, never fatal.
Exit code 0 when every document was imported, 1 otherwise.

``anchors`` takes the given documents or every document of the asset store. ``--check``
reports what ``--write`` would do; ``--write`` declares ``Chunks.layoutStart`` when missing
(additive), writes only the chunks whose stored anchor differs from the plan (``set``; or
``clear`` where the plan has none) and reads every write back. Chunks whose text changed since
the plan are skipped. Exit code 0 when nothing is (check) or remains (write) to be done, 1
otherwise, 2 when refused.

Each run writes ``REPORT`` (totals) and ``REPORT.documents.jsonl`` (per document). Both steps
are rerun after an interruption; finished pages and unchanged chunks are skipped.
"""
import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

from semant_demo.maintenance.page_layout.anchors import MAX_EDIT_RATIO
from semant_demo.maintenance.page_layout.serialize import Params

CONCURRENCY = 8
QUERY_TIMEOUT = 120


def _parser() -> argparse.ArgumentParser:
    defaults = Params()
    p = argparse.ArgumentParser(prog="python -m semant_demo.maintenance.page_import", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    steps = p.add_subparsers(dest="step", required=True)
    for name in ("assets", "anchors"):
        step = steps.add_parser(name)
        step.add_argument("documents", nargs="*", type=UUID, metavar="DOCUMENT_ID")
        step.add_argument("--document-ids", type=Path, help="file with one document UUID per line")
        step.add_argument("--assets-dir", type=Path, help="the page asset store (default PAGE_ASSETS_DIR)")
    assets = steps.choices["assets"]
    assets.add_argument("--page-order", type=Path, required=True, help="page_order export (#571)")
    assets.add_argument("--report", type=Path, required=True)
    assets.add_argument("--line-confidence", type=float, default=defaults.line_confidence)
    assets.add_argument("--min-chunk-chars", type=int, default=defaults.min_chunk_chars)
    assets.add_argument("--max-chunk-chars", type=int, default=defaults.max_chunk_chars)
    assets.add_argument("--max-edit-ratio", type=float, default=MAX_EDIT_RATIO)
    anchors = steps.choices["anchors"]
    mode = anchors.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", type=Path, metavar="REPORT", help="report what --write would do (read-only)")
    mode.add_argument("--write", type=Path, metavar="REPORT", help="write the planned anchors")
    anchors.add_argument("--confirm-endpoint", metavar="HOST:PORT", help="with --write: the configured endpoint")
    anchors.add_argument("--concurrency", type=int, default=CONCURRENCY)
    return p


def _ids(args) -> list[UUID] | None:
    ids = list(args.documents)
    if args.document_ids:
        ids += [UUID(line.strip()) for line in args.document_ids.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")]
    return list(dict.fromkeys(ids)) or None


class WeaviateAnchors:
    """The chunk reads and anchor writes of the import, on one Weaviate collection."""

    def __init__(self, client, collection: str, with_anchor: bool):
        self.client, self.collection, self.with_anchor = client, collection, with_anchor

    async def read_chunks(self, document_id):
        from semant_demo.adapters.weaviate.layout_anchors import read_document_chunks
        return await read_document_chunks(self.client, self.collection, document_id, self.with_anchor)

    async def write(self, chunk_id, value):
        from semant_demo.adapters.weaviate.layout_anchors import write_layout_start
        await write_layout_start(self.client, self.collection, chunk_id, value)

    async def read_back(self, ids):
        from semant_demo.adapters.weaviate.layout_anchors import read_layout_starts
        return await read_layout_starts(self.client, self.collection, ids)


async def _main(argv: list[str]) -> int:
    from semant_demo.adapters.filesystem.page_assets import PageAssetStore
    from semant_demo.adapters.weaviate.client import connect_weaviate
    from semant_demo.adapters.weaviate.document_cleanup import resolve_collection
    from semant_demo.adapters.weaviate.layout_anchors import declare_layout_start, layout_start_state
    from semant_demo.config import Config
    from semant_demo.maintenance.page_import import run

    args = _parser().parse_args(argv)
    config = Config()
    root = args.assets_dir or (Path(config.PAGE_ASSETS_DIR) if config.PAGE_ASSETS_DIR else None)
    if root is None:
        print("No asset store: give --assets-dir or set PAGE_ASSETS_DIR", file=sys.stderr)
        return 2
    store = PageAssetStore(root)
    endpoint = f"{config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}"
    writing = args.step == "anchors" and args.write is not None
    if writing and args.confirm_endpoint != endpoint:
        print(f"Refusing to write: configured endpoint {endpoint}, --confirm-endpoint {args.confirm_endpoint}",
              file=sys.stderr)
        return 2
    if args.step == "assets":
        params = Params(args.line_confidence, args.min_chunk_chars, args.max_chunk_chars)
        if not 0 <= args.max_edit_ratio < 1 or not 0 < params.min_chunk_chars <= params.max_chunk_chars:
            print("Need 0 <= --max-edit-ratio < 1 and 0 < --min-chunk-chars <= --max-chunk-chars", file=sys.stderr)
            return 2
    print(f"Weaviate endpoint ({'write' if writing else 'read-only'}): {endpoint}; asset store: {root}",
          file=sys.stderr)
    client = await connect_weaviate(config, query_timeout=QUERY_TIMEOUT)
    try:
        chunks = await resolve_collection(client, config.collectionNames.chunks_collection_name)
        state = await layout_start_state(client, chunks)
        if state == "conflict":
            print(f"{chunks}.layoutStart is declared differently; refusing", file=sys.stderr)
            return 2
        if writing and state == "missing":
            await declare_layout_start(client, chunks)
            state = "declared"
        anchors = WeaviateAnchors(client, chunks, with_anchor=state == "declared")
        if args.step == "assets":
            summary = await run.run_assets(store, run.read_exports(args.page_order, _ids(args)), anchors.read_chunks,
                                           params, args.max_edit_ratio, args.report)
            code = run.assets_exit_code(summary)
        else:
            ids = _ids(args) or store.documents()
            summary = await run.run_anchors(store, ids, anchors, writing, args.concurrency,
                                            args.write or args.check, endpoint)
            code = run.anchors_exit_code(summary)
        print({"statuses": summary["statuses"], "totals": summary["totals"]}, file=sys.stderr)
        return code
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
