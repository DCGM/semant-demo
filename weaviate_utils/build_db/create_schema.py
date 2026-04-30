import weaviate
from weaviate.classes.config import DataType, Property, ReferenceProperty


# Drop in reverse-dependency order so removing a target doesn't fail because
# some other collection still references it.
COLLECTIONS_IN_DROP_ORDER = [
    "Span",
    "Chunks",
    "Documents",
    "Tag",
    "UserCollection",
]


def drop_existing(client) -> None:
    for name in COLLECTIONS_IN_DROP_ORDER:
        if client.collections.exists(name):
            print(f"Dropping {name}")
            client.collections.delete(name)


def create_usercollection(client) -> None:
    client.collections.create(
        "UserCollection",
        properties=[
            Property(name="name", data_type=DataType.TEXT,
                     description="Name of the collection"),
            Property(name="user_id", data_type=DataType.TEXT,
                     description="ID of the user who owns the collection"),
            Property(name="description", data_type=DataType.TEXT,
                     description="Description of the collection"),
            Property(name="color", data_type=DataType.TEXT,
                     description="Color associated with the collection for UI purposes"),
            Property(name="created_at", data_type=DataType.DATE,
                     description="Date of creation of the collection"),
            Property(name="updated_at", data_type=DataType.DATE,
                     description="Date of last update of the collection"),
            Property(name="owner", data_type=DataType.TEXT),
        ],
    )


def create_tag(client) -> None:
    client.collections.create(
        "Tag",
        properties=[
            Property(name="tag_name", data_type=DataType.TEXT),
            Property(name="tag_shorthand", data_type=DataType.TEXT),
            Property(name="tag_color", data_type=DataType.TEXT),
            Property(name="tag_pictogram", data_type=DataType.TEXT),
            Property(name="tag_definition", data_type=DataType.TEXT),
            Property(name="tag_examples", data_type=DataType.TEXT_ARRAY),
            Property(name="collection_name", data_type=DataType.TEXT),
        ],
        references=[
            ReferenceProperty(
                name="userCollection",
                target_collection="UserCollection",
            ),
        ],
    )


def create_documents(client) -> None:
    client.collections.create(
        "Documents",
        properties=[
            Property(name="title", data_type=DataType.TEXT),
            Property(name="url", data_type=DataType.UUID),
            Property(name="public", data_type=DataType.BOOL),
            Property(name="documentType", data_type=DataType.TEXT),
            Property(name="titleMetadata", data_type=DataType.TEXT),
            Property(name="partNumber", data_type=DataType.TEXT),
            Property(name="dateIssued", data_type=DataType.DATE),
            Property(name="yearIssued", data_type=DataType.NUMBER),
            Property(name="yearIssuedMetadata", data_type=DataType.NUMBER),
            Property(name="language", data_type=DataType.TEXT),
            Property(name="dateIssuedMetadata", data_type=DataType.DATE),
            Property(name="publisher", data_type=DataType.TEXT),
            Property(name="placeOfPublication", data_type=DataType.TEXT),
            Property(name="subtitle", data_type=DataType.TEXT),
            Property(name="editors", data_type=DataType.TEXT_ARRAY),
            Property(name="partName", data_type=DataType.TEXT),
            Property(name="seriesName", data_type=DataType.TEXT),
            Property(name="edition", data_type=DataType.TEXT),
            Property(name="author", data_type=DataType.TEXT_ARRAY),
            Property(name="illustrators", data_type=DataType.TEXT_ARRAY),
            Property(name="translators", data_type=DataType.TEXT_ARRAY),
            Property(name="manufacturePublisher", data_type=DataType.TEXT),
            Property(name="manufacturePlaceTerm", data_type=DataType.TEXT),
            Property(name="seriesNumber", data_type=DataType.TEXT),
            Property(name="redaktors", data_type=DataType.TEXT_ARRAY),
        ],
        references=[
            ReferenceProperty(
                name="collection",
                target_collection="UserCollection",
                description="Reference to collection the document belongs to",
            ),
        ],
    )


def create_chunks(client) -> None:
    client.collections.create(
        "Chunks",
        properties=[
            Property(name="end_paragraph", data_type=DataType.BOOL),
            Property(name="from_page", data_type=DataType.INT),
            Property(name="language", data_type=DataType.TEXT),
            Property(name="start_page_id", data_type=DataType.TEXT),
            Property(name="text", data_type=DataType.TEXT),
            Property(name="to_page", data_type=DataType.INT),
            Property(name="title", data_type=DataType.TEXT),
            Property(name="order", data_type=DataType.INT),
        ],
        references=[
            ReferenceProperty(name="document", target_collection="Documents"),
            ReferenceProperty(name="userCollection", target_collection="UserCollection"),
            ReferenceProperty(name="automaticTag", target_collection="Tag"),
            ReferenceProperty(name="positiveTag", target_collection="Tag"),
            ReferenceProperty(name="negativeTag", target_collection="Tag"),
        ],
    )

def create_span(client) -> None:
    client.collections.create(
        "Span",
        properties=[
            Property(name="start", data_type=DataType.INT),
            Property(name="end", data_type=DataType.INT),
            Property(name="type", data_type=DataType.TEXT),
            Property(name="tagId", data_type=DataType.UUID),
            Property(name="chunkId", data_type=DataType.UUID),
            Property(name="reason", data_type=DataType.TEXT),
            Property(name="confidence", data_type=DataType.NUMBER),
        ],
        references=[
            ReferenceProperty(name="tag", target_collection="Tag"),
            ReferenceProperty(name="text_chunk", target_collection="Chunks"),
        ],
    )


def main() -> None:
    client = weaviate.connect_to_local(
        port=8082,
        grpc_port=50053,
    )
    try:
        drop_existing(client)

        # Create in dependency order (reverse of drop order).
        create_usercollection(client)
        create_tag(client)
        create_documents(client)
        create_chunks(client)
        create_span(client)

        print("Schema created:")
        for name in reversed(COLLECTIONS_IN_DROP_ORDER):
            print(f"  - {name}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
