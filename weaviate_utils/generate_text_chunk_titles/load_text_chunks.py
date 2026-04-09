#!/usr/bin/env python3
import argparse
import json

from weaviate import WeaviateClient
from weaviate.collections.classes.grpc import QueryReference
from weaviate.connect import ConnectionParams
from tqdm import tqdm


def parse_args():
    parser = argparse.ArgumentParser(description="Load text chunks from Weaviate database and print them as JSONl to stdout")

    parser.add_argument('--host', type=str, default="localhost", help='Weaviate host')
    parser.add_argument('--http_port', type=int, default=8080, help='Weaviate HTTP port')
    parser.add_argument('--grpc_port', type=int, default=50051, help='Weaviate gRPC port')
    parser.add_argument('--secure', action='store_true', help='Use secure connection')

    return parser.parse_args()


def main():
    args = parse_args()

    # Connect to Weaviate using CLI parameters.
    client = WeaviateClient(
        connection_params=ConnectionParams.from_params(
            http_host=args.host,
            http_port=args.http_port,
            http_secure=args.secure,
            grpc_host=args.host,
            grpc_port=args.grpc_port,
            grpc_secure=args.secure,
        )
    )

    with client:
        # Access the collection named "Chunks"
        chunks_collection = client.collections.get("Chunks")

        total = len(chunks_collection)
        # Iterate through all records in the collection
        for item in tqdm(chunks_collection.iterator(return_references=QueryReference(link_on="document", return_properties=["title"])), total=total, desc="Loading text chunks"):
            record_id = item.uuid
            record_text = item.properties.get("text")
            language = item.properties.get("language")

            referenced_docs = item.references.get("document")

            for doc in referenced_docs.objects:
                document_id = doc.uuid
                document_title = doc.properties.get("title")
                break

            print(json.dumps({
                "id": str(document_id)+"/"+str(record_id),
                "language": language,
                "document_title": document_title,
                "text": record_text,
            }, ensure_ascii=False))


if __name__ == "__main__":
    main()
