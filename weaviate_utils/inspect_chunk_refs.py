import argparse
from uuid import UUID

from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
from weaviate.classes.query import QueryReference


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Validate that Chunks.document references point to real Documents "
            "objects and include document data."
        )
    )
    parser.add_argument("--chunk-collection", type=str, default="Chunks", help="Name of the chunk collection.")
    parser.add_argument("--document-ref", type=str, default="document", help="Reference name on chunk object.")
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=1000,
        help="Maximum number of chunks to inspect (default: 1000).",
    )
    parser.add_argument("--sample-limit", type=int, default=10, help="How many failing examples to print.")
    parser.add_argument("--http_host", type=str, default="localhost", help="HTTP host for weaviate client.")
    parser.add_argument("--http_port", type=int, default=8080, help="HTTP port for weaviate client.")
    parser.add_argument("--grpc_host", type=str, default="localhost", help="grpc host for weaviate client.")
    parser.add_argument("--grpc_port", type=int, default=50051, help="grpc port for weaviate client.")
    return parser.parse_args()


def stringify_uuid(value: UUID | str) -> str:
    return str(value)


def main():
    args = parse_args()

    client = WeaviateClient(
        connection_params=ConnectionParams.from_params(
            http_host=args.http_host,
            http_port=args.http_port,
            http_secure=False,
            grpc_host=args.grpc_host,
            grpc_port=args.grpc_port,
            grpc_secure=False,
        )
    )

    try:
        client.connect()

        if not client.is_ready():
            print("ERROR: Weaviate is not ready.")
            return

        chunks = client.collections.get(args.chunk_collection)

        print(f"Inspecting collection '{args.chunk_collection}' reference '{args.document_ref}'")

        total_chunks = 0
        chunks_with_ref_data = 0
        missing_ref_field = 0
        empty_ref_targets = 0
        docs_with_data = 0
        docs_missing_data = 0
        unique_doc_ids = set()
        failing_examples = []
        stopped_at_limit = False

        for chunk in chunks.iterator(
            return_references=[
                QueryReference(
                    link_on=args.document_ref,
                    return_properties=["title", "author", "yearIssued", "publisher"],
                )
            ]
        ):
            if total_chunks >= args.max_chunks:
                stopped_at_limit = True
                break

            total_chunks += 1
            refs = chunk.references or {}
            doc_ref = refs.get(args.document_ref)

            if doc_ref is None:
                missing_ref_field += 1
                if len(failing_examples) < args.sample_limit:
                    failing_examples.append(
                        f"chunk={chunk.uuid}: reference field '{args.document_ref}' is missing"
                    )
                continue

            targets = doc_ref.objects if doc_ref.objects else []
            if not targets:
                empty_ref_targets += 1
                if len(failing_examples) < args.sample_limit:
                    failing_examples.append(
                        f"chunk={chunk.uuid}: reference '{args.document_ref}' has no targets"
                    )
                continue

            chunks_with_ref_data += 1

            for doc in targets:
                unique_doc_ids.add(stringify_uuid(doc.uuid))
                props = doc.properties or {}
                if props:
                    docs_with_data += 1
                else:
                    docs_missing_data += 1
                    if len(failing_examples) < args.sample_limit:
                        failing_examples.append(
                            f"chunk={chunk.uuid}: target document={doc.uuid} has empty properties"
                        )

        print("\n=== Summary ===")
        print(f"Total chunks scanned: {total_chunks}")
        print(f"Chunks with non-empty '{args.document_ref}' targets: {chunks_with_ref_data}")
        print(f"Chunks missing reference field '{args.document_ref}': {missing_ref_field}")
        print(f"Chunks with empty '{args.document_ref}' targets: {empty_ref_targets}")
        print(f"Referenced documents with data: {docs_with_data}")
        print(f"Referenced documents with empty data: {docs_missing_data}")
        print(f"Unique referenced document IDs: {len(unique_doc_ids)}")
        if stopped_at_limit:
            print(f"Scan stopped at max chunk limit: {args.max_chunks}")

        if failing_examples:
            print("\n=== Sample problems ===")
            for line in failing_examples:
                print(f"- {line}")
        else:
            print("\nNo reference/data issues found in scanned chunks.")

    finally:
        client.close()


if __name__ == "__main__":
    main()