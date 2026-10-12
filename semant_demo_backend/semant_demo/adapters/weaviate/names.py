"""The configured names of the Weaviate collections and reference properties."""
from pydantic import BaseModel


class CollectionNames(BaseModel):
    chunks_collection_name: str
    tag_collection_name: str
    user_collection_name: str
    document_collection_name: str
    span_collection_name: str
    user_collection_link_name: str
    tag_to_user_collection_link_name: str
