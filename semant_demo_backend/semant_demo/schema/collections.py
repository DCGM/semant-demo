from pydantic import BaseModel
from uuid import UUID
from uuid import UUID
from datetime import datetime

class Collection(BaseModel):
    id: UUID
    name: str
    user_id: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
    color: str
    
class PostCollection(BaseModel):
    name: str
    user_id: str
    description: str | None = None
    color: str
    
class PatchCollection(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None