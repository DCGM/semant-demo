import asyncio
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="Print all data in Weaviate database.")
    parser.add_argument("--http_host", type=str, default="localhost", help="HTTP host for weaviate client.")
    parser.add_argument("--http_port", type=int,default=8080, help="HTTP port for weaviate client.")
    parser.add_argument("--grpc_host", type=str, default="localhost", help="grpc host for weaviate client.")
    parser.add_argument("--grpc_port", type=int, default=50051, help="grpc port for weaviate client.")
    return parser.parse_args()

def main():
    args = parse_args()

    # Connect to your Weaviate instance
    client = WeaviateClient(
        connection_params=ConnectionParams.from_params(
            http_host=args.http_host, http_port=args.http_port, http_secure=False,
            grpc_host=args.grpc_host, grpc_port=args.grpc_port, grpc_secure=False,
        )
    )
    client.connect()

    # Get all collections
    collections = client.collections.list_all()
    print(f"Found {len(collections)} collections.\n")

    for name in collections:
        print(f"=== Collection: {name} ===")

        # Get the collection object
        collection = client.collections.get(name)

        # Get the record count
        count = collection.aggregate.over_all(total_count=True).total_count
        print(f"Record count: {count}")

        # Get the schema of the collection
        schema = collection.config.get()
        print("Schema:")
        print("Properties:")
        for prop in schema.properties:
            print(f"- name: {prop.name}")
            print(f"  description: {prop.description}")
            print(f"  type: {prop.data_type.value}")
            print("\n")

    # Close the connection
    client.close()

if __name__ == "__main__":
    main()


