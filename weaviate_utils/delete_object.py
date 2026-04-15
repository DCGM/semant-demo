import weaviate

client = weaviate.connect_to_local(
    port=8080,
    grpc_port=50051,
)

collection_name = "Usercollection_test"
id="7fcf6da2-9325-48e7-9e24-bbf359c43ac0"

collection = client.collections.use(collection_name)

collection.data.delete_by_id(
    id
)

client.close()