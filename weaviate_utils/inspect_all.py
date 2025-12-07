import asyncio
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams

def main():
    # Connect to your Weaviate instance
    client = WeaviateClient(
        connection_params=ConnectionParams.from_params(
            http_host="localhost", http_port=8080, http_secure=False,
            grpc_host="localhost", grpc_port=50051, grpc_secure=False,
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
        print(schema)
        print("\n")

    # Close the connection
    client.close()

if __name__ == "__main__":
    main()


