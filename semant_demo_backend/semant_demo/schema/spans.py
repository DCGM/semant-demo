from pydantic import BaseModel

from semant_demo.schemas import SpanType

class PostSpan(BaseModel):
    start: int
    end: int
    type: SpanType
    
    chunkId: str
    tagId: str
    
class PatchSpan(BaseModel):
    start: int | None = None
    end: int | None = None
    type: SpanType | None = None

    tagId: str | None = None