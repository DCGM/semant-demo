from pydantic import BaseModel, model_validator
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

    @model_validator(mode="after")
    def check_at_least_one_field_set(self) -> "PatchTag":
        if not self.model_dump(exclude_unset=True, exclude_none=True):
            raise ValueError("At least one field must be provided for update")
        return self