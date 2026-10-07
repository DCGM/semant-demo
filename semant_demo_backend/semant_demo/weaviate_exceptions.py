"""Legacy Weaviate-named errors, still raised by the span and text chunk adapters.

New code raises the neutral errors in ``semant_demo.core.errors`` and lets SDK errors
propagate. Remove this module when the span/text chunk adapters have moved (#205/#206).
"""


class WeaviateError(Exception):
    """Base exception for all weaviate errors."""
    pass

# Specific exceptions
class WeaviateConnectError(WeaviateError):
    """
    Raised when unable to connect to Weaviate instance.
    """
    pass


class WeaviateDataValidationError(WeaviateError):
    """
    Raised when input data validation fails.
    
    Common causes:
    - Empty required field (name, UUID, etc.)
    - Invalid UUID format
    - Invalid data type
    - Conflicting parameters
    - Missing required fields
    """
    pass

class WeaviateLimitError(WeaviateError):
    """
    Raised when Weaviate limit is exceeded.
    
    Common causes:
    - Too many requests in short time
    - Batch operation too large
    - Insufficient resources on Weaviate server
    """
    pass

class WeaviateServerError(WeaviateError):
    """
    Raised when Weaviate server returns an error.
    
    Common causes:
    - Internal server error (5xx)
    - Unexpected server response
    - Protocol error
    """
    pass

class WeaviateOperationError(WeaviateError):
    """
    Raised when invalid weaviate operation is called
    like attemting to create a duplicate that should be unique or object not found error.
    
    Causes:
    - Creating tag with name that already exists for user
    - Creating collection with duplicate name
    - Calling object which does not exist
    """
    pass
