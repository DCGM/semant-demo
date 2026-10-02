class WeaviateError(Exception):
    """
    Base class for domain-level (non-SDK) Weaviate errors raised by this app.

    SDK/infrastructure failures (connection, timeout, query, server errors)
    are not wrapped here - they propagate as weaviate.exceptions.WeaviateBaseError
    and its subclasses. A custom hierarchy only adds value for business-rule
    errors that the Weaviate SDK itself has no concept of.
    """
    pass


class NotFoundError(WeaviateError):
    """
    Raised when a requested object does not exist.

    Weaviate itself returns None / an empty result for a missing object
    rather than raising - domain code raises this to signal "not found"
    to its callers.

    Recommended HTTP mapping: 404.
    """
    pass


class ConflictError(WeaviateError):
    """
    Raised when an operation would violate an app-enforced uniqueness or
    state constraint that Weaviate itself does not check (e.g. a tag with
    the same name already exists for this user/collection).

    Recommended HTTP mapping: 409.
    """
    pass


# --- Deprecated: 1:1 wrappers around weaviate.exceptions.WeaviateBaseError subtypes ---
#
# These still exist only because semant_demo/weaviate_utils/{helpers,tag,span,
# text_chunk,user_collection}.py and their routes import and raise/catch them.
# Do not use them in new code - let SDK exceptions (weaviate.exceptions.WeaviateBaseError
# and subclasses) propagate directly instead, and use NotFoundError/ConflictError above
# for business-rule errors. Remove each of these once the file(s) that still reference
# it have been migrated (see the weaviate_utils cleanup roadmap).

class WeaviateConnectError(WeaviateError):
    """Deprecated - superseded by weaviate.exceptions.WeaviateConnectionError. Do not use in new code."""
    pass


class WeaviateDataValidationError(WeaviateError):
    """Deprecated - input validation belongs in Pydantic request schemas. Do not use in new code."""
    pass


class WeaviateLimitError(WeaviateError):
    """Deprecated - superseded by weaviate.exceptions.WeaviateTimeoutError. Do not use in new code."""
    pass


class WeaviateServerError(WeaviateError):
    """Deprecated - superseded by weaviate.exceptions.WeaviateBaseError subtypes. Do not use in new code."""
    pass


class WeaviateOperationError(WeaviateError):
    """Deprecated - superseded by NotFoundError/ConflictError above. Do not use in new code."""
    pass
