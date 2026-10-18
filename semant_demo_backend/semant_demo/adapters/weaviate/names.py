"""The configured names of the Weaviate collections and reference properties."""
from pydantic import BaseModel


class CollectionNames(BaseModel):
    chunks_collection_name: str
    tag_collection_name: str
    user_collection_name: str
    document_collection_name: str
    span_collection_name: str
    """The legacy, single-tenant span collection: only the source of the annotation migration (#327)."""
    annotation_collection_name: str
    """The multi-tenant annotation collection, one tenant per user collection (#327)."""
    user_collection_link_name: str
    tag_to_user_collection_link_name: str
