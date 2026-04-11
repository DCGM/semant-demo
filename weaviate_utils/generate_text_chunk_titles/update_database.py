#!/usr/bin/env python3
# Updating database with titles and order

import argparse
import json
import time
from pathlib import Path

import weaviate.classes.config as wvc
from tqdm import tqdm
from weaviate import WeaviateClient
from weaviate.config import AdditionalConfig, Timeout
from weaviate.connect import ConnectionParams
from weaviate.exceptions import WeaviateTimeoutError


def parse_args():
    parser = argparse.ArgumentParser(
        description="Update chunk title/order fields in a Weaviate collection from JSONL files."
    )
    parser.add_argument("chunks_directory", type=str)
    parser.add_argument(
        "--chunk-collection",
        type=str,
        default="Chunks_test",
        help="Weaviate chunk collection to update",
    )
    parser.add_argument("--host", type=str, default="localhost", help="Weaviate host")
    parser.add_argument("--http_port", type=int, default=8080, help="Weaviate HTTP port")
    parser.add_argument("--grpc_port", type=int, default=50051, help="Weaviate gRPC port")
    parser.add_argument("--secure", action="store_true", help="Use secure connection")
    parser.add_argument("--from_doc", type=int, default=0, help="Starts updating from given document index")

    return parser.parse_args()


def get_document_file_paths(chunks_directory: str) -> dict[str, Path]:
    """
    Gets a mapping from document ID to the file path of the corresponding text chunks.

    :param chunks_directory: directory with text chunk files, each file should be named {doc_id}.jsonl and contain text chunks for the document with id doc_id
    :return:
     doc_id: file_path
    """

    document_file_paths: dict[str, Path] = {}

    for jsonl_file in Path(chunks_directory).glob("**/*.jsonl"):
        doc_id = jsonl_file.stem
        document_file_paths[doc_id] = jsonl_file

    return document_file_paths


def _extract_property_names(collection_config) -> set[str]:
    names: set[str] = set()
    properties = getattr(collection_config, "properties", None) or []
    for prop in properties:
        if hasattr(prop, "name"):
            names.add(prop.name)
        elif isinstance(prop, dict) and "name" in prop:
            names.add(prop["name"])
    return names


def ensure_required_chunk_properties(chunk_collection) -> None:
    # `simple=True` works on newer clients; fallback keeps compatibility.
    try:
        config = chunk_collection.config.get(simple=True)
    except TypeError:
        config = chunk_collection.config.get()

    existing_property_names = _extract_property_names(config)

    if "title" not in existing_property_names:
        chunk_collection.config.add_property(
            wvc.Property(name="title", data_type=wvc.DataType.TEXT)
        )

    if "order" not in existing_property_names:
        chunk_collection.config.add_property(
            wvc.Property(name="order", data_type=wvc.DataType.INT)
        )


def update_chunk_records(chunk_collection, file_path: Path, counters: dict[str, int]) -> None:
    with open(file_path, "r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            counters["total_lines"] += 1

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                counters["invalid_json"] += 1
                continue

            text_chunk_id = record.get("id")
            title = record.get("title")
            order = record.get("order")

            if text_chunk_id is None or title is None or order is None:
                counters["missing_fields"] += 1
                continue

            try:
                order = int(order)
            except (TypeError, ValueError):
                counters["invalid_order"] += 1
                continue

            for i in range(3):
                try:
                    chunk_collection.data.update(
                        uuid=text_chunk_id,
                        properties={"title": title, "order": order},
                    )
                    counters["updated"] += 1
                    break
                except WeaviateTimeoutError as e:
                    if i == 2:
                        raise e
                    time.sleep(120)


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
        ),
        additional_config=AdditionalConfig(
            timeout=Timeout(
                init=60,     # connect/startup timeout
                query=120,   # read/query operations
                insert=180,  # writes/updates
            )
        ),
    )

    counters = {
        "total_lines": 0,
        "invalid_json": 0,
        "missing_fields": 0,
        "invalid_order": 0,
        "updated": 0,
    }

    try:
        client.connect()

        if not client.is_ready():
            raise RuntimeError("Weaviate is not ready.")

        chunk_collection = client.collections.get(args.chunk_collection)
        ensure_required_chunk_properties(chunk_collection)

        document_file_paths = get_document_file_paths(args.chunks_directory)

        cnt = -1
        for _, file_path in tqdm(
            document_file_paths.items(),
            total=len(document_file_paths),
            desc="Updating database",
        ):
            cnt += 1
            if cnt < args.from_doc:
                continue
            update_chunk_records(chunk_collection, file_path, counters)

    finally:
        client.close()

    print("Update complete.")
    print(f"Total records seen: {counters['total_lines']}")
    print(f"Updated records: {counters['updated']}")
    print(f"Invalid JSON lines: {counters['invalid_json']}")
    print(f"Missing required fields (id/title/order): {counters['missing_fields']}")
    print(f"Invalid order values: {counters['invalid_order']}")


if __name__ == "__main__":
    main()
