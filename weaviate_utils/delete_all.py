import weaviate

client = weaviate.connect_to_local(
    port=8082,
    grpc_port=50053,
)

client.collections.delete_all()

client.close()