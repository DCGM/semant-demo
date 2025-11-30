import json
import os
import argparse
import glob
import random
from tqdm import tqdm
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
import numpy as np
import weaviate.classes.config as wvc
import re
import datetime
import logging

logging.basicConfig(level=logging.WARNING)

def parse_args():
    parser = argparse.ArgumentParser(description="Create DB schema, red document json and push documents into db, read text cunks from jsonl files and push to DB.")
    parser.add_argument("--source-dir", type=str, required=True, help="Where to read source .jsonl and .json files from.")
    parser.add_argument("--delete-old", action="store_true", help="Delete old collections before creating new ones.")
    parser.add_argument("--document-collection", type=str, default="Documents", help="Name of the document collection.")
    parser.add_argument("--chunk-collection", type=str, default="Chunks", help="Name of the text chunk collection.")
    parser.add_argument('--vector-file-suffix', type=str, default='_embeddings.npy', help="Suffix for the vector files. Default is '_embeddings.npy'.")
    parser.add_argument("--owner-name", type=str, required=False, help="Collection name.")
    args = parser.parse_args()
    return args


document_column_types = {
    "library": wvc.DataType.TEXT,
    "title": wvc.DataType.TEXT,
    "subTitle": wvc.DataType.TEXT,
    "partNumber": wvc.DataType.INT,
    "partName": wvc.DataType.TEXT,
    "yearIssued": wvc.DataType.INT,
    "dateIssued": wvc.DataType.DATE,
    "authors": wvc.DataType.TEXT_ARRAY,
    "publisher": wvc.DataType.TEXT,
    "description": wvc.DataType.TEXT,
    "url": wvc.DataType.TEXT,
    "public": wvc.DataType.BOOL,
    "documentType": wvc.DataType.TEXT,
    "keywords": wvc.DataType.TEXT_ARRAY,
    "genre": wvc.DataType.TEXT,
    "placeTerm": wvc.DataType.TEXT,

    "section": wvc.DataType.TEXT,  # Section of the document
    "region": wvc.DataType.TEXT,  # Region of the document
    "id_code": wvc.DataType.TEXT,  # Identifier code for the document
}

column_mapping = {
    "year": "yearIssued",
    "author": "authors",
    "date": "dateIssued",
    "source": "library",
}

chunk_column_types = {
    "text": wvc.DataType.TEXT,
    "start_page_id": wvc.DataType.TEXT,
    "from_page": wvc.DataType.INT,
    "to_page": wvc.DataType.INT,
    "end_paragraph": wvc.DataType.BOOL,
    "language": wvc.DataType.TEXT,
    "ner_A": wvc.DataType.TEXT_ARRAY,  # Address entities
    "ner_G": wvc.DataType.TEXT_ARRAY,  # Geographical entities
    "ner_I": wvc.DataType.TEXT_ARRAY,  # Institution entities
    "ner_M": wvc.DataType.TEXT_ARRAY,  # Media entities
    "ner_N": wvc.DataType.TEXT_ARRAY,  # ???
    "ner_O": wvc.DataType.TEXT_ARRAY,  # Cultural artifacts
    "ner_P": wvc.DataType.TEXT_ARRAY,  # Person entities
    "ner_T": wvc.DataType.TEXT_ARRAY,  # Temporal entities
}


def create_document_collection(client: WeaviateClient, keys: list[str], collection_name: str) -> None:
    properties = []
    unknown_keys = set()
    for key in keys:
        if key in document_column_types:
            properties.append(wvc.Property(name=key, data_type=document_column_types[key]))
        else:
            properties.append(wvc.Property(name=key, data_type=wvc.DataType.TEXT))
            unknown_keys.add(key)

    client.collections.create(
        name=collection_name,
        properties=properties,
    )


def create_chunk_schema(client: WeaviateClient, keys: list[str], chunk_collection_name: str, document_collection_name: str) -> None:
    properties = []
    unknown_keys = set()
    for key in keys:
        if key in chunk_column_types:
            properties.append(wvc.Property(name=key, data_type=chunk_column_types[key]))
        else:
            properties.append(wvc.Property(name=key, data_type=wvc.DataType.TEXT))
            unknown_keys.add(key)

    client.collections.create(
        name=chunk_collection_name,
        vector_index_config=wvc.Configure.VectorIndex.hnsw(),
        properties=properties,
        references=[
            wvc.ReferenceProperty(
                name="document",
                target_collection=document_collection_name,
                cardinality="1"
            )
        ]
    )


def extract_attributes_from_jsonl(source_dir: str, max_files=500) -> list[str]:
    files = glob.glob(os.path.join(source_dir, "*.jsonl"))
    if len(files) > max_files:
        files = random.sample(files, max_files)
    attributes = set()
    for file_name in files:
        with open(file_name, 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f.readlines()]
            lines = [line for line in lines if line]  # Remove empty lines
            for line in lines:
                data = json.loads(line)
                attributes.update(data.keys())
    return sorted(attributes)


def parse_date(date_str: str) -> str:
    if re.match(r'\d{1,2}\.\d{1,2}\.\d{4}', date_str):
        date_match = re.search(r'\d{1,2}\.\d{1,2}\.\d{4}', date_str)
        date_str = date_match.group(0)
        return datetime.datetime.strptime(date_str, '%d.%m.%Y').isoformat() + "+00:00"

    logging.warning(f"Date format not recognized: {date_str}")
    return None


def insert_documents(client: WeaviateClient, source_dir: str, document_collection: str) -> None:
    doc_col = client.collections.get(document_collection)
    json_files = glob.glob(os.path.join(source_dir, "*.jsonl"))
    inserted_document_uuids = set()

    for json_file in tqdm(json_files, desc="Inserting documents"):
        with open(json_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as e:
                    logging.error(f"Error decoding JSON from file {json_file}: {e}")
                    continue

                uuid = data["document"]
                if uuid in inserted_document_uuids:
                    continue
                inserted_document_uuids.add(uuid)

                # map keys
                data = {column_mapping.get(k, k): v for k, v in data.items()}
                data = {k: v for k, v in data.items() if k in document_column_types}

                if "authors" in data and isinstance(data["authors"], str):
                    data["authors"] = data["authors"].split(';')
                if "keywords" in data and isinstance(data["keywords"], str):
                    data["keywords"] = data["keywords"].split(';')
                if "dateIssued" in data:
                    data["dateIssued"] = parse_date(data["dateIssued"])
                    data["yearIssued"] = datetime.datetime.fromisoformat(data["dateIssued"]).year

                data = {k: v for k, v in data.items() if v is not None and k in document_column_types}
                doc_col.data.insert(
                    uuid=uuid,
                    properties=data,
                )


def insert_chunks(client: WeaviateClient, source_dir: str, chunk_collection: str, vector_file_suffix: str = '_embeddings.npy') -> None:
    jsonl_files = glob.glob(os.path.join(source_dir, "*.jsonl"))
    with client.batch.fixed_size(batch_size=32, concurrent_requests=2) as batch:
        for jsonl_file in tqdm(jsonl_files, desc="Inserting chunks"):
            vectors = np.load(jsonl_file.replace('.jsonl', vector_file_suffix), allow_pickle=True)

            with open(jsonl_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    data = {column_mapping.get(k, k): v for k, v in data.items()}
                    
                    if 'id' not in data:
                        continue
                    
                    uuid = data["id"]
                    document_uuid = data.get("document")
                    
                    if not document_uuid:
                        logging.warning(f"No document reference for chunk {uuid}. Skipping.")
                        continue
                    
                    vector = data.get("vector")
                    
                    if vector is None:
                        if "vector_index" in data:
                            vector = vectors[data["vector_index"]]
                        else:
                            logging.warning(f"No vector found for chunk {uuid} in file {jsonl_file}. Skipping.")
                            continue

                    # Filter properties - exclude reference fields and metadata
                    properties = {k: v for k, v in data.items() if k in chunk_column_types}
                    
                    batch.add_object(
                        uuid=uuid,
                        collection=chunk_collection,
                        properties=properties,  # Only actual properties
                        vector=vector,
                        references={
                            "document": document_uuid  # References go here
                        }
                    )


def main():
    args = parse_args()

    # Connect to Weaviate
    client = WeaviateClient(
        connection_params= ConnectionParams.from_params(
            http_host="localhost", http_port=8080, http_secure=False,
            grpc_host="localhost", grpc_port=50051, grpc_secure=False,
        ))
    client.connect()
    if not client.is_ready():
        print("Weaviate is not ready.")
        return

    if args.delete_old:
        # Delete old collections if specified
        try:
            client.collections.delete(args.document_collection)
            client.collections.delete(args.chunk_collection)
        except Exception as e:
            print(f"Error deleting old collections: {e}")

    keys = extract_attributes_from_jsonl(args.source_dir)

    mapped_keys = [column_mapping.get(k, k) for k in keys]
    document_keys = [k for k in mapped_keys if k in document_column_types]
    chunk_keys = [k for k in mapped_keys if k in chunk_column_types]
    missing_keys = set(mapped_keys) - set(document_keys) - set(chunk_keys)

    print(f"Keys in JSONL files: {mapped_keys}")
    print(f"Document keys: {document_keys}")
    print(f"Chunk keys: {chunk_keys}")
    print(f"Missing keys: {missing_keys}")

    # Create schema
    create_document_collection(client, document_keys, args.document_collection)
    create_chunk_schema(client, chunk_keys, args.chunk_collection, args.document_collection)

    # Insert documents and chunks
    insert_documents(client, args.source_dir, args.document_collection)
    insert_chunks(client, args.source_dir, args.chunk_collection, args.vector_file_suffix)
    client.close()

if __name__ == "__main__":
    main()