"""Application errors that services and adapters raise independently of the storage SDK.

``create_app`` maps them to HTTP responses (``NotFoundError`` -> 404,
``InvalidRequestError`` -> 400). Storage/SDK failures are not wrapped: they propagate
and become 500 responses.
"""


class NotFoundError(Exception):
    """The requested object does not exist (or the caller may not know that it exists)."""


class InvalidRequestError(Exception):
    """The request is well formed but cannot be carried out, e.g. sharing with the owner."""
