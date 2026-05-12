"""Export annotation statistics for a set of UserCollections to CSV.

Background
----------
In this app, a logical "test collection" is materialised as multiple
``UserCollection`` clones (one per annotating user). All clones share the same
``Documents`` / ``Chunks`` (via multiple references) but each clone has its
own ``Tag`` objects (with identical ``tag_name``). User annotations are stored
as ``Span`` objects referencing one of the user's tags and a (shared) chunk.

This script takes one ``UserCollection`` UUID per user, walks all chunks of
all documents in those collections, and writes a long-format CSV with one row
per (chunk, user, tag_name) combination::

    nazev_dokumentu, id_chunku, username, nazev_tagu, anotace

where ``anotace`` is 1 if the user has a *positive*-type Span on that chunk
referencing their Tag with the matching ``tag_name``, otherwise 0.

Usage
-----
    python annotation_stats.py \
        --collection-ids <uuid1> <uuid2> ... \
        --output annotations.csv \
        [--http_port 8080] [--grpc_port 50051]
"""

from __future__ import annotations

import argparse
import csv
import sys
from uuid import UUID

from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
from weaviate.classes.query import Filter, QueryReference


PAGE_SIZE = 200
# In Weaviate the Span.type property stores the short enum value ("pos", "neg",
# "auto") -- see semant_demo.schemas.SpanType.
POSITIVE_TYPE = "pos"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--collection-ids", nargs="+",
                   help="UserCollection UUIDs (one per annotating user).")
    g.add_argument("--collection-file",
                   help=("Path to a text file with one entry per line in the "
                         "format 'username:uuid' (username is a note for the "
                         "human reader and is ignored at runtime -- the CSV "
                         "always uses the 'owner' field from the DB). Lines "
                         "starting with '#' and blank lines are ignored. A "
                         "line containing only a UUID is also accepted."))
    p.add_argument("--output", default="annotations.csv", help="Output CSV path.")
    p.add_argument("--http_host", default="localhost")
    p.add_argument("--http_port", type=int, default=8080)
    p.add_argument("--grpc_host", default="localhost")
    p.add_argument("--grpc_port", type=int, default=50051)
    p.add_argument("--user-collection", default="UserCollection")
    p.add_argument("--tag-collection", default="Tag")
    p.add_argument("--document-collection", default="Documents")
    p.add_argument("--chunk-collection", default="Chunks")
    p.add_argument("--span-collection", default="Span")
    return p.parse_args()


def load_collection_file(path: str) -> list[tuple[str, str | None]]:
    """Parse a 'username:uuid' (or 'uuid') file into [(uuid, username_or_None)].

    Empty lines and lines starting with '#' are skipped.
    """
    entries: list[tuple[str, str | None]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                name, _, uuid_str = line.partition(":")
                name = name.strip() or None
                uuid_str = uuid_str.strip()
            else:
                name = None
                uuid_str = line
            if not uuid_str:
                print(f"ERROR: {path}:{lineno}: missing UUID", file=sys.stderr)
                sys.exit(2)
            entries.append((uuid_str, name))
    return entries


def validate_uuids(ids):
    for cid in ids:
        try:
            UUID(cid)
        except ValueError:
            print(f"ERROR: '{cid}' is not a valid UUID", file=sys.stderr)
            sys.exit(2)


def fetch_user(client, user_collection_name: str, coll_id: str):
    uc = client.collections.get(user_collection_name)
    obj = uc.query.fetch_object_by_id(coll_id)
    if obj is None:
        raise SystemExit(f"UserCollection {coll_id} not found.")
    props = obj.properties or {}
    owner = props.get("owner") or props.get("name") or coll_id
    return owner


def iter_by_ref(coll, ref_name: str, target_id: str, return_references=None):
    """Yield all objects in ``coll`` referencing ``target_id`` via ``ref_name``.

    Weaviate's cursor API (``after``) cannot be combined with ``where`` filters,
    so we paginate with ``offset`` instead.
    """
    flt = Filter.by_ref(ref_name).by_id().equal(target_id)
    offset = 0
    while True:
        res = coll.query.fetch_objects(
            filters=flt, limit=PAGE_SIZE, offset=offset,
            return_references=return_references,
        )
        if not res.objects:
            return
        for o in res.objects:
            yield o
        if len(res.objects) < PAGE_SIZE:
            return
        offset += PAGE_SIZE


def fetch_tags(client, tag_collection_name: str, coll_id: str):
    """Return list of (tag_uuid_str, tag_name) for given UserCollection."""
    coll = client.collections.get(tag_collection_name)
    out = []
    for t in iter_by_ref(coll, "userCollection", coll_id):
        props = t.properties or {}
        name = props.get("tag_name")
        if name:
            out.append((str(t.uuid), name))
    return out


def fetch_documents(client, document_collection_name: str, coll_id: str):
    """Return list of (doc_uuid_str, title) for documents in the collection."""
    coll = client.collections.get(document_collection_name)
    out = []
    for d in iter_by_ref(coll, "collection", coll_id):
        props = d.properties or {}
        title = props.get("title") or str(d.uuid)
        out.append((str(d.uuid), title))
    return out


def fetch_chunks_for_collection(client, chunk_collection_name: str, coll_id: str):
    """Yield (chunk_uuid_str, document_uuid_str) for every chunk that explicitly
    belongs to ``coll_id`` (via Chunks.userCollection reference).

    Only a subset of a document's chunks is typically linked to a given
    UserCollection, so we must filter by ``userCollection`` -- filtering only
    by ``document`` would include chunks that do not belong to this collection.
    """
    coll = client.collections.get(chunk_collection_name)
    for c in iter_by_ref(
        coll, "userCollection", coll_id,
        return_references=[QueryReference(link_on="document")],
    ):
        doc_ref = (c.references or {}).get("document")
        doc_id = str(doc_ref.objects[0].uuid) if doc_ref and doc_ref.objects else None
        yield str(c.uuid), doc_id


def fetch_positive_span_map(client, span_collection_name: str, tag_uuids: set[str]):
    """Build set of (chunk_id, tag_id) for every positive-type Span.

    We page through all positive spans once, then keep only those whose tag is
    in ``tag_uuids`` (cheaper than filtering by ref-in-list which Weaviate
    doesn't always support cleanly).
    """
    coll = client.collections.get(span_collection_name)
    flt = Filter.by_property("type").equal(POSITIVE_TYPE)
    offset = 0
    result: set[tuple[str, str]] = set()
    total = 0
    while True:
        res = coll.query.fetch_objects(
            filters=flt, limit=PAGE_SIZE, offset=offset,
            return_references=[
                QueryReference(link_on="tag"),
                QueryReference(link_on="text_chunk"),
            ],
        )
        if not res.objects:
            break
        for s in res.objects:
            refs = s.references or {}
            tag_ref = refs.get("tag")
            chunk_ref = refs.get("text_chunk")
            tag_id = str(tag_ref.objects[0].uuid) if tag_ref and tag_ref.objects else None
            chunk_id = str(chunk_ref.objects[0].uuid) if chunk_ref and chunk_ref.objects else None
            if tag_id and chunk_id and tag_id in tag_uuids:
                result.add((chunk_id, tag_id))
        total += len(res.objects)
        if len(res.objects) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    print(f"[i] Scanned {total} positive spans, kept {len(result)} relevant (chunk,tag) pairs.")
    return result


def main():
    args = parse_args()

    if args.collection_file:
        entries = load_collection_file(args.collection_file)
    else:
        entries = [(cid, None) for cid in args.collection_ids]

    if not entries:
        print("ERROR: no collection ids provided.", file=sys.stderr)
        sys.exit(2)

    collection_ids = [cid for cid, _ in entries]
    validate_uuids(collection_ids)

    client = WeaviateClient(
        connection_params=ConnectionParams.from_params(
            http_host=args.http_host, http_port=args.http_port, http_secure=False,
            grpc_host=args.grpc_host, grpc_port=args.grpc_port, grpc_secure=False,
        )
    )

    try:
        client.connect()
        if not client.is_ready():
            print("ERROR: Weaviate is not ready.", file=sys.stderr)
            sys.exit(1)

        # 1) per-user: owner name + their tags ----------------------------------
        users = []  # list[ {coll_id, owner, tags_by_name: dict[str,str]} ]
        all_tag_names: set[str] = set()
        all_tag_uuids: set[str] = set()
        for cid in collection_ids:
            owner = fetch_user(client, args.user_collection, cid)
            tags = fetch_tags(client, args.tag_collection, cid)
            tags_by_name: dict[str, str] = {}
            for tuuid, tname in tags:
                # if same tag_name appears multiple times, keep first
                tags_by_name.setdefault(tname, tuuid)
                all_tag_uuids.add(tuuid)
                all_tag_names.add(tname)
            print(f"[i] {cid}  owner={owner!r}  tags={len(tags_by_name)}")
            users.append({"coll_id": cid, "owner": owner, "tags_by_name": tags_by_name})

        if not all_tag_names:
            print("WARNING: no tags found across given collections; CSV will have no rows.")

        # 2) documents + chunks (only chunks that belong to one of the
        #    requested collections; dedup by chunk UUID across clones) --------
        documents: dict[str, str] = {}  # doc_id -> title
        for cid in collection_ids:
            for did, title in fetch_documents(client, args.document_collection, cid):
                documents.setdefault(did, title)
        print(f"[i] Documents linked to collections: {len(documents)}")

        # chunk_id -> doc_id (deduplicated; a chunk may be linked to several
        # clones but we only want it once in the output)
        chunks_by_id: dict[str, str] = {}
        for cid in collection_ids:
            for chid, did in fetch_chunks_for_collection(client, args.chunk_collection, cid):
                if did is None:
                    continue
                chunks_by_id.setdefault(chid, did)
        print(f"[i] Chunks belonging to collections: {len(chunks_by_id)}")

        # Build the iteration list (doc_title, doc_id, chunk_id); fall back
        # to doc_id when the document isn't in our `documents` map (shouldn't
        # happen with consistent data but is cheap to guard).
        doc_chunks: list[tuple[str, str, str]] = []
        for chid, did in chunks_by_id.items():
            title = documents.get(did, did)
            doc_chunks.append((title, did, chid))

        # 3) all positive spans -> (chunk, tag) set ------------------------------
        positive = fetch_positive_span_map(client, args.span_collection, all_tag_uuids)

        # 4) write CSV -----------------------------------------------------------
        sorted_tag_names = sorted(all_tag_names)
        rows_written = 0
        with open(args.output, "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["nazev_dokumentu", "id_chunku", "username", "nazev_tagu", "anotace"])
            for doc_title, _did, chunk_id in doc_chunks:
                for user in users:
                    owner = user["owner"]
                    for tag_name in sorted_tag_names:
                        tag_uuid = user["tags_by_name"].get(tag_name)
                        if tag_uuid is None:
                            annotation = 0
                        else:
                            annotation = 1 if (chunk_id, tag_uuid) in positive else 0
                        writer.writerow([doc_title, chunk_id, owner, tag_name, annotation])
                        rows_written += 1

        print(f"[OK] Wrote {rows_written} rows to {args.output}")

    finally:
        client.close()


if __name__ == "__main__":
    main()
