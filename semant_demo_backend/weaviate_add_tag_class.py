import weaviate
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
from semant_demo.config import config
import weaviate.classes.config as wvc
from weaviate.classes.config import ReferenceProperty

def setup_schema():
    conn_params = ConnectionParams.from_params(
        http_host="localhost", http_port=8080, http_secure=False,
        grpc_host="localhost", grpc_port=50051, grpc_secure=False,
    )
    client = WeaviateClient(connection_params=conn_params)
    try:
        client.connect()
        # Check if Tag class already exists
        if client.collections.exists("Tag"):
            print(f"Tag schema: {client.collections.get('Tag').config.get()}")
            print("Tag class already exists")
            client.collections.delete("Tag") # remove the class
        # create the Tag class
        # TODO rename remove tag_name name
        client.collections.create(name="Tag",
                properties=[
                    {"name": "tag_name", "data_type": wvc.DataType.TEXT},
                    {"name": "tag_shorthand", "data_type": wvc.DataType.TEXT},
                    {"name": "tag_color", "data_type": wvc.DataType.TEXT},
                    {"name": "tag_pictogram", "data_type": wvc.DataType.TEXT},
                    {"name": "tag_definition", "data_type": wvc.DataType.TEXT},
                    {"name": "tag_examples", "data_type": wvc.DataType.TEXT_ARRAY},
                    {"name": "collection_name", "data_type": wvc.DataType.TEXT}
                ]
            )
        print("Tag class created successfully")

         # Check if ChunkTagApproval class already exists
        if client.collections.exists("ChunkTagApproval"):
            print(f"ChunkTagApproval schema: {client.collections.get('ChunkTagApproval').config.get()}")
            print("ChunkTagApproval class already exists")
            client.collections.delete("ChunkTagApproval") # remove the class
        # create the ChunkTagApproval class
        client.collections.create(name="ChunkTagApproval",
                properties=[
                    {"name": "approved", "data_type": wvc.DataType.BOOL},
                    {"name": "user", "data_type": wvc.DataType.TEXT},
                ],
                references=[
                    ReferenceProperty(
                        name="hasChunk",
                        target_collection="Chunks"
                    ),
                    ReferenceProperty(
                        name="hasTag",
                        target_collection="Tag"
                    )
                ]
            )
        print("TagRef class created successfully")

        """Update the Chunks class schema to include hasTags and hasApprovals reference"""
        try:
            if client.collections.exists("Chunks"):
                chunks_collection = client.collections.get("Chunks")
                config = chunks_collection.config.get()
                print("Chunks collection configuration:")
                print(f"Properties: {config.properties}")
                # check if hasTags property exists
                has_tags = any(ref.name == "hasTags" for ref in config.references)
                print(f"hasTags property exists: {has_tags}")
                if not has_tags:
                    chunks_collection.config.add_reference(
                        weaviate.classes.config.ReferenceProperty(name="hasTags", target_collection="Tag",  # OBJECT for references
                        )
                    )
                    print("Successfully added hasTags reference to Chunks collection")
                """
                # check if hasApprovals property exists
                has_approvals = any(ref.name == "hasApprovals" for ref in config.references)
                print(f"hasApprovals property exists: {has_approvals}")
                if not has_approvals:
                    chunks_collection.config.add_reference(
                        weaviate.classes.config.ReferenceProperty(name="hasApprovals", target_collection="ChunkTagApproval",  # OBJECT for references
                        )
                    )
                    print("Successfully added hasApprovals reference to Chunks collection")
                """
            else:
                print("Chunks collection does not exist")
                
        except Exception as e:
            print(f"Error checking Chunks schema: {e}")
    except Exception as e:
        print(e)
    finally:
        client.close()

if __name__ == "__main__":
    setup_schema()