"""HTTP models of the collection export (#656)."""
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CollectionExportRequest(BaseModel):
    collection_ids: list[UUID] = Field(min_length=1)
    """The collections to export, each readable by the user (owner or member); repeated ids
    count once, in the order first given."""

    @field_validator("collection_ids")
    @classmethod
    def _unique(cls, ids: list[UUID]) -> list[UUID]:
        return list(dict.fromkeys(ids))


class CollectionExportTicket(BaseModel):
    download_path: str
    """Where the browser downloads the export (``GET``, no sign-in header: the path is the
    credential). Valid once, for ``expires_in`` seconds."""
    expires_in: int
