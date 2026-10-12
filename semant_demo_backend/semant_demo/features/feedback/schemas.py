"""Application feedback HTTP models."""
from pydantic import BaseModel


class AppFeedbackRequest(BaseModel):
    type: str
    subject: str | None = None
    message: str
    email: str | None = None
