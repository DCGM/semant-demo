from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.exceptions import (
    WeaviateConnectionError,
    WeaviateTimeoutError,
    WeaviateQueryError,
    WeaviateInvalidInputError,
    UnexpectedStatusCodeError,
    ResponseCannotBeDecodedError,
    WeaviateClosedClientError,
    InsufficientPermissionsError,
)
from semant_demo.weaviate_exceptions import (
    WeaviateConnectError, 
    WeaviateDataValidationError, 
    WeaviateLimitError, 
    WeaviateServerError, 
    WeaviateOperationError 
)

import semant_demo.schemas as schemas
from semant_demo.weaviate_utils.helpers import WeaviateHelpers

class Document():
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames
        self.helpers = WeaviateHelpers(client, collectionNames)

    #######
    # API #
    #######
    def read():
        pass
    
    def search():
        pass

    ###########
    # Helpers #
    ###########