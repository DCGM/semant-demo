
from pydantic import BaseModel
from uuid import UUID

class Tag(BaseModel):
    id: UUID
    name: str
    shorthand: str
    color: str
    pictogram: str
    definition: str
    examples: list[str]

class PostTag(BaseModel):
    name: str
    shorthand: str
    color: str
    pictogram: str
    definition: str
    examples: list[str] = []
    
class PatchTag(BaseModel):
    name: str | None = None
    shorthand: str | None = None
    color: str | None = None
    pictogram: str | None = None
    definition: str | None = None
    examples: list[str] | None = None