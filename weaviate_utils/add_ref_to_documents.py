import weaviate
from weaviate.classes.config import ReferenceProperty

client = weaviate.connect_to_local(
    port=8080,
    grpc_port=50051,
)

try:
    documents = client.collections.get("Documents_test")
    documents.config.add_reference(
        ReferenceProperty(
            name="collection",
            target_collection="Usercollection_test",
            description="Reference to collection the document belongs to"
        )
    )

finally:
    client.close()
