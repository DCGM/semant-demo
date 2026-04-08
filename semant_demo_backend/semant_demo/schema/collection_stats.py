from pydantic import BaseModel
from uuid import UUID

class CollectionStats(BaseModel):
    collectionId: UUID
    documentsCount: int
    chunksCount: int
    annotationsCount: int
    tagsCount: int