import weaviate

client = weaviate.connect_to_local(
    port=8080,
    grpc_port=50051,
)

collection_name = "TagSpan2_test"

client.collections.delete(
    collection_name
)

client.close()