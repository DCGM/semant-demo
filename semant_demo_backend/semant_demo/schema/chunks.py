from pydantic import BaseModel
from uuid import UUID

class Chunk(BaseModel):
    id: UUID
    text: str
    start_page_id: UUID
    from_page: int
    to_page: int
    end_paragraph: bool = True
    title: str | None = None
    language: str | None = None
    order: int
    in_collection: bool = False