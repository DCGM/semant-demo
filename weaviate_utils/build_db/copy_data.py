"""Copy documents (and their chunks) from production Weaviate to the local
test instance. Skips UserCollection and Tag — copies Documents + Chunks and
preserves the `document` reference on each chunk so backend search works.

Production:  localhost:8080  (gRPC 50051)
Test:        localhost:8082  (gRPC 50053)

Usage:
    python copy_data.py --limit 500
"""

from __future__ import annotations

import argparse
from typing import Any

import weaviate
from weaviate.classes.query import Filter


def _normalize_vector(vector: Any) -> Any:
    if isinstance(vector, dict):
        return vector.get("default") or next(iter(vector.values()), None)
    return vector


def fetch_documents(src, limit: int) -> list[Any]:
    coll = src.collections.get("Documents")
    res = coll.query.fetch_objects(limit=limit, include_vector=True)
    return list(res.objects)


def fetch_chunks_for_document(coll, doc_uuid: str, page_size: int = 500) -> list[Any]:
    out: list[Any] = []
    after: str | None = None
    flt = Filter.by_ref("document").by_id().equal(doc_uuid)
    while True:
        res = coll.query.fetch_objects(
            filters=flt,
            limit=page_size,
            after=after,
            include_vector=True,
        )
        objs = list(res.objects)
        if not objs:
            break
        out.extend(objs)
        if len(objs) < page_size:
            break
        after = str(objs[-1].uuid)
    return out


def insert_one(coll, obj: Any) -> bool:
    try:
        coll.data.insert(
            properties=dict(obj.properties or {}),
            uuid=str(obj.uuid),
            vector=_normalize_vector(obj.vector),
        )
        return True
    except Exception as e:
        print(f"  ! insert failed for {obj.uuid}: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--src-port", type=int, default=8080)
    parser.add_argument("--src-grpc", type=int, default=50051)
    parser.add_argument("--dst-port", type=int, default=8082)
    parser.add_argument("--dst-grpc", type=int, default=50053)
    args = parser.parse_args()

    src = weaviate.connect_to_local(port=args.src_port, grpc_port=args.src_grpc)
    dst = weaviate.connect_to_local(port=args.dst_port, grpc_port=args.dst_grpc)

    try:
        print(f"Fetching {args.limit} documents from prod...")
        documents = fetch_documents(src, args.limit)
        print(f"  got {len(documents)} documents")
        if not documents:
            return

        src_chunks = src.collections.get("Chunks")
        dst_docs = dst.collections.get("Documents")
        dst_chunks = dst.collections.get("Chunks")

        docs_ok = 0
        chunks_ok = 0
        chunks_total = 0

        for i, doc in enumerate(documents, 1):
            chunks = fetch_chunks_for_document(src_chunks, str(doc.uuid))
            chunks_total += len(chunks)
            print(f"[{i}/{len(documents)}] doc {doc.uuid}: {len(chunks)} chunks")

            if insert_one(dst_docs, doc):
                docs_ok += 1

            if not chunks:
                continue

            doc_uuid = str(doc.uuid)
            with dst_chunks.batch.dynamic() as batch:
                for ch in chunks:
                    batch.add_object(
                        properties=dict(ch.properties or {}),
                        uuid=str(ch.uuid),
                        vector=_normalize_vector(ch.vector),
                        references={"document": doc_uuid},
                    )

            failed = dst_chunks.batch.failed_objects
            if failed:
                print(f"  ! {len(failed)} chunk inserts failed (first: {failed[0]})")
            chunks_ok += len(chunks) - len(failed)

        print(
            f"\nDone. Inserted {docs_ok}/{len(documents)} documents and "
            f"{chunks_ok}/{chunks_total} chunks."
        )
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    main()
