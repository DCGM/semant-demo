"""Clone a UserCollection to another user.

What it does:
- Creates a new UserCollection owned by the target user (same name/description/
  color/owner-display).
- Adds references on every Document and Chunk that points at the source
  collection so they also point at the new one (no data duplication).
- Recreates every Tag of the source collection as a new Tag linked to the new
  collection (props copied verbatim).
- Spans are NOT copied.
- Chunk-level tag refs (positiveTag/negativeTag/automaticTag) are NOT remapped.

Usage:
    python clone_collection.py \
        --source-id <source_collection_uuid> \
        --new-user-id <target_user_id> \
        [--new-owner-name "Display Name"] \
        [--new-name "Cloned name"] \
        [--port 8080] [--grpc 50051]
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import weaviate
from weaviate.classes.query import Filter


PAGE_SIZE = 200


def fetch_source_collection(client, source_id: str) -> Any:
    coll = client.collections.get("UserCollection")
    obj = coll.query.fetch_object_by_id(source_id)
    if obj is None:
        raise SystemExit(f"Source UserCollection {source_id} not found.")
    return obj


def create_new_collection(
    client,
    source: Any,
    new_user_id: str,
    new_owner_name: str | None,
    new_name: str | None,
) -> str:
    coll = client.collections.get("UserCollection")
    props = dict(source.properties or {})
    now = datetime.now(timezone.utc)
    new_props = {
        "name": new_name or props.get("name"),
        "user_id": new_user_id,
        "description": props.get("description"),
        "color": props.get("color"),
        "created_at": now,
        "updated_at": now,
        "owner": new_owner_name if new_owner_name is not None else props.get("owner"),
    }
    new_uuid = coll.data.insert(properties=new_props)
    print(f"[+] Created new UserCollection {new_uuid} for user_id={new_user_id}")
    return str(new_uuid)


def iter_objects_by_ref(coll, ref_name: str, target_id: str):
    """Yield all objects in `coll` that reference `target_id` via `ref_name`."""
    flt = Filter.by_ref(ref_name).by_id().equal(target_id)
    after: str | None = None
    while True:
        res = coll.query.fetch_objects(
            filters=flt,
            limit=PAGE_SIZE,
            after=after,
        )
        objs = list(res.objects)
        if not objs:
            return
        for o in objs:
            yield o
        if len(objs) < PAGE_SIZE:
            return
        after = str(objs[-1].uuid)


def link_documents(client, source_id: str, new_id: str) -> int:
    coll = client.collections.get("Documents")
    n = 0
    for doc in iter_objects_by_ref(coll, "collection", source_id):
        try:
            coll.data.reference_add(
                from_uuid=doc.uuid,
                from_property="collection",
                to=new_id,
            )
            n += 1
        except Exception as e:
            print(f"  ! document {doc.uuid} link failed: {e}")
    print(f"[+] Linked {n} documents to new collection")
    return n


def link_chunks(client, source_id: str, new_id: str) -> int:
    coll = client.collections.get("Chunks")
    n = 0
    for ch in iter_objects_by_ref(coll, "userCollection", source_id):
        try:
            coll.data.reference_add(
                from_uuid=ch.uuid,
                from_property="userCollection",
                to=new_id,
            )
            n += 1
            if n % 500 == 0:
                print(f"    ... {n} chunks linked")
        except Exception as e:
            print(f"  ! chunk {ch.uuid} link failed: {e}")
    print(f"[+] Linked {n} chunks to new collection")
    return n


def clone_tags(client, source_id: str, new_id: str) -> int:
    coll = client.collections.get("Tag")
    n = 0
    for tag in iter_objects_by_ref(coll, "userCollection", source_id):
        props = dict(tag.properties or {})
        new_tag_props = {
            "tag_name": props.get("tag_name"),
            "tag_shorthand": props.get("tag_shorthand"),
            "tag_color": props.get("tag_color"),
            "tag_pictogram": props.get("tag_pictogram"),
            "tag_definition": props.get("tag_definition"),
            "tag_examples": list(props.get("tag_examples") or []),
            "collection_name": props.get("collection_name"),
        }
        try:
            new_tag_uuid = coll.data.insert(properties=new_tag_props)
            coll.data.reference_add(
                from_uuid=new_tag_uuid,
                from_property="userCollection",
                to=new_id,
            )
            n += 1
        except Exception as e:
            print(f"  ! tag {tag.uuid} clone failed: {e}")
    print(f"[+] Cloned {n} tags into new collection")
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description="Clone a UserCollection to another user.")
    parser.add_argument("--source-id", required=True, help="UUID of the source UserCollection.")
    parser.add_argument("--new-user-id", required=True, help="user_id of the target user.")
    parser.add_argument("--new-owner-name", default=None,
                        help="Display name for the target owner (defaults to copying source owner).")
    parser.add_argument("--new-name", default=None,
                        help="Override the collection name (defaults to source name).")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--grpc", type=int, default=50051)
    args = parser.parse_args()

    try:
        UUID(args.source_id)
    except ValueError:
        print("source-id must be a valid UUID", file=sys.stderr)
        sys.exit(2)

    client = weaviate.connect_to_local(port=args.port, grpc_port=args.grpc)
    try:
        source = fetch_source_collection(client, args.source_id)
        src_name = (source.properties or {}).get("name")
        print(f"[i] Source collection: {args.source_id}  name={src_name!r}")

        new_id = create_new_collection(
            client, source, args.new_user_id, args.new_owner_name, args.new_name
        )

        link_documents(client, args.source_id, new_id)
        link_chunks(client, args.source_id, new_id)
        clone_tags(client, args.source_id, new_id)

        print(f"\nDone. New collection UUID: {new_id}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
