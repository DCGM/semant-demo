import weaviate
from weaviate.classes.config import Property, DataType

client = weaviate.connect_to_local(
    port=8080,
    grpc_port=50051,
)

try:
    user_collections = client.collections.get("UserCollection")
    user_collections.config.add_property(
        Property(
            name="shared_with",
            data_type=DataType.UUID_ARRAY
        )
    )

finally:
    client.close()
