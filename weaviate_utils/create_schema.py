from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
import weaviate.classes.config as wvc
import weaviate
# Build ConnectionParams with both http and grpc blocks
conn_params = ConnectionParams.from_params(
    http_host="localhost", http_port=8080, http_secure=False,
    grpc_host="localhost", grpc_port=50051, grpc_secure=False,
)

# Instantiate the client
client = WeaviateClient(connection_params=conn_params)
client.connect()
print(client.is_ready())

# Optional: clean slate
for cls in ("UserCollection", "Document", "TextChunk", "Chunks", "Tag"):
    try:
        client.collections.delete(cls)
    except Exception as e:
        pass

# 3) create UserCollection - kolekcie chunkov
client.collections.create(
    name="UserCollection",
    vector_index_config=wvc.Configure.VectorIndex.hnsw(),
    properties=[
        wvc.Property(name="name",    data_type=wvc.DataType.TEXT),
        wvc.Property(name="user_id", data_type=wvc.DataType.TEXT),
    ]
)

# 4) Create Document (with a reverse reference slot for collections)
client.collections.create(
    name="Document",
    vector_index_config=wvc.Configure.VectorIndex.hnsw(),
    properties=[
        wvc.Property(name="title",            data_type=wvc.DataType.TEXT),
        wvc.Property(name="subtitle",         data_type=wvc.DataType.TEXT),
        wvc.Property(name="partNumber",       data_type=wvc.DataType.INT),
        wvc.Property(name="partName",         data_type=wvc.DataType.TEXT),
        wvc.Property(name="yearIssued",       data_type=wvc.DataType.INT),
        wvc.Property(name="dateIssued",       data_type=wvc.DataType.DATE),
        wvc.Property(name="author",           data_type=wvc.DataType.TEXT_ARRAY),
        wvc.Property(name="publisher",        data_type=wvc.DataType.TEXT),
        wvc.Property(name="language",         data_type=wvc.DataType.TEXT_ARRAY),
        wvc.Property(name="description",      data_type=wvc.DataType.TEXT),
        wvc.Property(name="url",              data_type=wvc.DataType.TEXT),
        wvc.Property(name="public",           data_type=wvc.DataType.BOOL),
        wvc.Property(name="documentType",     data_type=wvc.DataType.TEXT),
        wvc.Property(name="keywords",         data_type=wvc.DataType.TEXT_ARRAY),
        wvc.Property(name="genre",            data_type=wvc.DataType.TEXT),
        wvc.Property(name="placeOfPublication", data_type=wvc.DataType.TEXT),
        # Many-to-many: Document → UserCollection

    ],
    references=[
        wvc.ReferenceProperty(
            name="collections",
            target_collection="UserCollection",
            cardinality="*"
        )
    ]
)

# 5) Create Tag to store different tags and their attributes
client.collections.create(
    name="Tag",
    properties=[
        wvc.Property(name="tag_name", data_type=wvc.DataType.TEXT),
        wvc.Property(name="tag_shorthand", data_type=wvc.DataType.TEXT),
        wvc.Property(name="tag_color", data_type=wvc.DataType.TEXT),
        wvc.Property(name="tag_pictogram", data_type=wvc.DataType.TEXT),
        wvc.Property(name="tag_definition", data_type=wvc.DataType.TEXT),
        wvc.Property(name="tag_examples", data_type=wvc.DataType.TEXT_ARRAY),
        wvc.Property(name="collection_name", data_type=wvc.DataType.TEXT),
    ],
    references=[
        wvc.ReferenceProperty(  # add reference to chunk collections created by user
            name="userCollection",
            target_collection="UserCollection",
            cardinality="*"
        ),
    ]
)

# 6) Create TextChunk (with reference back to its Document)
client.collections.create(
    name="Chunks", # TextChunk
    vector_index_config=wvc.Configure.VectorIndex.hnsw(),
    properties=[
        wvc.Property(name="text", data_type=wvc.DataType.TEXT),
    ],
    references=[
        wvc.ReferenceProperty(
            name="document",
            target_collection="Document",
            cardinality="*"
        ),
        wvc.ReferenceProperty(  # add reference to chunk collections created by user
            name="userCollection",
            target_collection="UserCollection",
            cardinality="*"
        ),
        wvc.ReferenceProperty(
            name="automaticTag",
            target_collection="Tag",
            cardinality="1"
        ),
        wvc.ReferenceProperty(
            name="positiveTag",
            target_collection="Tag",
            cardinality="1"
        ),
        wvc.ReferenceProperty(
            name="negativeTag",
            target_collection="Tag",
            cardinality="1"
        ),
    ]
)

client.close()

print("Schema created: UserCollection, Document, TextChunk, Tag")