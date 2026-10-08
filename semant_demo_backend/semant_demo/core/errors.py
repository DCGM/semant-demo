"""Application errors that services and adapters raise independently of the storage SDK.

``create_app`` maps them to HTTP responses (``NotFoundError`` -> 404,
``InvalidRequestError`` -> 400, ``IncompleteWriteError`` -> 500 with a structured body).
Other storage/SDK failures are not wrapped: they propagate and become 500 responses.
"""


class NotFoundError(Exception):
    """The requested object does not exist (or the caller may not know that it exists)."""


class InvalidRequestError(Exception):
    """The request is well formed but cannot be carried out, e.g. sharing with the owner."""


class IncompleteWriteError(Exception):
    """A multi-step write of one object stopped part way (ADR 0002).

    Used where the API has no result body for partial outcomes (tag creation, tag and
    collection deletion). Completed steps are kept; ``create_app`` answers 500 with
    ``detail`` (a readable message), ``step`` (the step that failed), ``completed``
    (counts of completed steps) and ``uncertain`` (the failed write timed out and may
    have been applied).
    """

    def __init__(self, detail: str, *, step: str, completed: dict[str, int] | None = None,
                 uncertain: bool = False):
        super().__init__(detail)
        self.detail = detail
        self.step = step
        self.completed = dict(completed or {})
        self.uncertain = uncertain

    def body(self) -> dict:
        return {"detail": self.detail, "step": self.step, "completed": self.completed,
                "uncertain": self.uncertain}
