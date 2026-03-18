class WeaviateOperationError(Exception):
    """Base exception for all weaviate errors."""
    pass

# Specific exceptions

class WeaviateConnectionError(WeaviateOperationError):
    """
    Raised when unable to connect to Weaviate instance.
    """
    pass

class WeaviateSchemaError(WeaviateOperationError):
    """
    Raised when Weaviate client calls invalid schema.
    
    Causes:
    - Collection schema doesn't exist
    - Collection schema is invalid
    """
    pass

class WeaviateDeleteError(WeaviateOperationError):
    """
    Raised when deletion cannot be performed due to not existing object.
    
    Common causes:
    - Attempting to delete already-deleted object
    """
    pass

class WeaviateDuplicateError(WeaviateOperationError):
    """
    Raised when attempting to create a duplicate that should be unique.
    
    Causes:
    - Creating tag with name that already exists for user
    - Creating collection with duplicate name
    """
    pass

class WeaviateFilterError(WeaviateOperationError):
    """
    Raised when filter specification is invalid.
    
    Common causes:
    - Invalid filter syntax
    - Filtering on non-existent property
    - Invalid operator for property type
    - Malformed Filter object
    """
    pass
 
 
class WeaviateQueryError(WeaviateOperationError):
    """
    Raised when query execution fails.
    
    Common causes:
    - Query timeout
    - Invalid query structure
    - Query syntax error
    """
    pass
 
 
class WeaviateReferenceError(WeaviateOperationError):
    """
    Raised when reference operation fails.
    
    Common causes:
    - Creating reference to non-existent object
    - Invalid reference property
    - Reference already exists
    """
    pass
 
class WeaviateNotFoundError(WeaviateOperationError):
    """
    Raised when requested object/s cannot be found.
    
    Common causes:
    - Query returns no results
    - Object UUID doesn't exist
    - Collection name doesn't exist
    - Tag name doesn't exist
    """
    pass 
 
class WeaviateLimitError(WeaviateOperationError):
    """
    Raised when Weaviate limit is exceeded.
    
    Common causes:
    - Too many requests in short time
    - Batch operation too large
    - Insufficient resources on Weaviate server
    """
    pass
 
class WeaviateServerError(WeaviateOperationError):
    """
    Raised when Weaviate server returns an error.
    
    Common causes:
    - Internal server error (5xx)
    - Unexpected server response
    - Protocol error
    """
    pass
 
 
class WeaviateSerializationError(WeaviateOperationError):
    """
    Raised when serializing/deserializing data fails.
    
    Common causes:
    - Non-JSON-serializable object
    - Invalid response format from server
    - Date/time format mismatch
    """
    pass
 
class WeaviateErrorContext:
    """
    Context manager for unified Weaviate error handling and logging.
    
    Usage:
        with WeaviateErrorContext("fetch_chunks"):
            # Weaviate SDK exceptions will be caught and re-raised as custom exceptions
            pass
    """
    
    def __init__(self, operation_name: str):
        self.operation_name = operation_name
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Implementation would map Weaviate SDK exceptions to custom exceptions
        return False