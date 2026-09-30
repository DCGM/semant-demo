import weaviate
from weaviate.classes.config import Property, DataType

client = weaviate.connect_to_local(
    port=8080,
    grpc_port=50051,
)

try:
    documents = client.collections.get("Usercollection_test")
    documents.config.add_property(
        Property(
            name="owner",
            data_type=DataType.TEXT
        )
    )

finally:
    client.close()
