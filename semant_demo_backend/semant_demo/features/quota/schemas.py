"""Daily LLM allowance HTTP models."""
import datetime
from typing import Literal

from pydantic import BaseModel, Field


class QuotaStatusResponse(BaseModel):
    principal: Literal["guest", "account"] = Field(description="Whose allowance: the guest cookie's or the account's")
    day: str = Field(description="The UTC calendar day (YYYY-MM-DD) the amounts belong to")
    limit_usd: float = Field(description="The day's allowance, a USD-equivalent estimate (not a bill)")
    used_usd: float = Field(description="charged_usd + reserved_usd")
    charged_usd: float = Field(description="Cost of the day's settled AI operations")
    reserved_usd: float = Field(description="Estimates held for AI operations not settled yet; an operation "
                                            "that never settles keeps its estimate charged")
    remaining_usd: float
    reset_at: datetime.datetime = Field(description="When the next UTC day and allowance start")
    near_limit: bool = Field(description="used_usd has reached the near-limit share of limit_usd")
    exhausted: bool = Field(description="Nothing is left, so every new AI operation is refused until reset_at "
                                         "(one whose estimate does not fit the remaining amount is refused earlier)")


class QuotaExhaustedResponse(BaseModel):
    """The body of a 429 answer to an AI operation refused for the daily allowance
    (``QuotaExhausted.body``); the answer also has a ``Retry-After`` header (seconds).
    AI routes declare it as their 429 response (``QUOTA_EXHAUSTED_RESPONSES``)."""
    detail: str
    code: Literal["llm_quota_exhausted"]
    principal: Literal["guest", "account"]
    reset_at: datetime.datetime
    limit_usd: float
    used_usd: float


QUOTA_EXHAUSTED_RESPONSES: dict[int | str, dict] = {429: {
    "model": QuotaExhaustedResponse,
    "description": "The caller's daily AI allowance has no room for the operation; nothing was generated.",
    "headers": {"Retry-After": {"description": "Seconds until the allowance resets (UTC midnight)",
                                "schema": {"type": "integer"}}}}}
"""``responses`` of a route whose AI operation is admitted against the daily allowance."""
