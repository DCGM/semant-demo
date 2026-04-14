import argparse
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
from weaviate.classes.query import Filter, QueryReference


def parse_args():
    parser = argparse.ArgumentParser(
        description="Scan documents and check which have chunks."
    )
    parser.add_argument("--limit", type=int, default=1000, help="Max documents to scan.")
    parser.add_argument("--http_host", type=str, default="localhost", help="HTTP host for weaviate client.")
    parser.add_argument("--http_port", type=int, default=8080, help="HTTP port for weaviate client.")
    parser.add_argument("--grpc_host", type=str, default="localhost", help="grpc host for weaviate client.")
    parser.add_argument("--grpc_port", type=int, default=50051, help="grpc port for weaviate client.")
    return parser.parse_args()


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

        documents = client.collections.get("Documents")
        chunks = client.collections.get("Chunks")

        print(f"Scanning documents for chunk associations (limit: {args.limit})...\n")

        docs_with_chunks = []
        docs_without_chunks = []
        scanned = 0

        # Fetch documents in batches
        offset = 0
        page_size = 100

        while scanned < args.limit:
            response = documents.query.fetch_objects(limit=page_size, offset=offset)

            if not response.objects:
                break

            for doc in response.objects:
                document_id = str(doc.uuid)

                # Count chunks for this document
                chunk_filter = Filter.by_ref("document").by_id().equal(document_id)
                try:
                    chunk_response = chunks.query.fetch_objects(
                        filters=chunk_filter,
                        limit=1,  # Just need to know if at least one exists
                    )
                    chunk_count = len(chunk_response.objects) if chunk_response.objects else 0
                except Exception as e:
                    print(f"  Error checking chunks for {document_id}: {e}")
                    chunk_count = 0

                if chunk_count > 0:
                    docs_with_chunks.append((document_id, chunk_count))
                else:
                    docs_without_chunks.append(document_id)

                scanned += 1
                if scanned % 100 == 0:
                    print(f"  Scanned {scanned} documents...")

                if scanned >= args.limit:
                    break

            offset += page_size

        print(f"\n=== Summary ===")
        print(f"Total documents scanned: {scanned}")
        print(f"Documents WITH chunks: {len(docs_with_chunks)}")
        print(f"Documents WITHOUT chunks: {len(docs_without_chunks)}")

        if docs_with_chunks:
            print(f"\nDocuments with chunks (first 20):")
            for doc_id, chunk_count in docs_with_chunks[:20]:
                print(f"  {doc_id}: {chunk_count} chunks")

        if docs_without_chunks:
            print(f"\nDocuments without chunks (first 20):")
            for doc_id in docs_without_chunks[:20]:
                print(f"  {doc_id}")

    finally:
        client.close()


if __name__ == "__main__":
    main()
