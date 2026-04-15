import weaviate
from weaviate.classes.config import Property, DataType, ReferenceProperty

client = weaviate.connect_to_local(
    port=8080,
    grpc_port=50051,
)

client.collections.create(
    "Span_test",
    properties=[
        Property(name="start", data_type=DataType.INT),
        Property(name="end", data_type=DataType.INT),
        Property(name="type", data_type=DataType.TEXT)   
    ],
    references=[
        ReferenceProperty(
            name="tag",
            target_collection="Tag_test"
        ),
        ReferenceProperty(
            name="text_chunk",
            target_collection="Chunks_test"
        )
    ]
)

client.close()