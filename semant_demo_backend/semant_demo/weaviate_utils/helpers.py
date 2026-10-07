"""Legacy helpers still used by the span and text chunk adapters.

Shared write helpers moved to ``semant_demo.adapters.weaviate.writes``; ``step_failure``
and ``guard_progress`` are re-exported here until the span adapter moves (#206).
"""
import logging

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter, QueryReference
from weaviate.exceptions import (
    WeaviateConnectionError,
    WeaviateTimeoutError,
    WeaviateQueryError,
    WeaviateInvalidInputError,
    UnexpectedStatusCodeError,
    ResponseCannotBeDecodedError,
)

from semant_demo import schemas
from semant_demo.adapters.weaviate.writes import guard_progress, step_failure  # noqa: F401
from semant_demo.weaviate_exceptions import WeaviateConnectError, WeaviateDataValidationError, WeaviateLimitError, WeaviateServerError, WeaviateOperationError


class WeaviateHelpers:
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames

    async def delete_span_cascade(self, span_id: str) -> None:
        """
        Performs cascade deletion of a span
        """
        logging.info(f"Performing cascade deletion of span {span_id}")
        span_collection = self.client.collections.get(
            self.collectionNames.span_collection_name)

        # delete the span itself
        await span_collection.data.delete_by_id(span_id)

    async def fetch_chunks(self, filters: Filter) -> list:
        """
        Fetches chunks with filters - tag, user-collection. Fetch subset of text chunks given by filters.

        Filters are built by the public methods using inline like:
            filters = Filter.by_property("name").equal("value")

        Args:
            filters: Weaviate Filter object for querying chunks

        Returns:
            List of chunk objects matching the filters

        Raises:
            WeaviateConnectError: Cannot connect to Weaviate instance
            WeaviateFilterError: Invalid filter specification or malformed Filter object
            WeaviateQueryError: Query execution failed or query syntax error
            WeaviateNotFoundError: No chunks found matching the filters
            WeaviateSerializationError: Cannot deserialize response from Weaviate
            WeaviateServerError: Weaviate server returned an error
        """
        # TODO use instead of:
        # fetch chunks from specific collection (currently used in get_tagged_chunks_paged, get_collection_chunks_paged)
        # fetch chunks by tags (currently used in filterChunksByTags)

        try:
            # prepare references to fetch in the query (set to None if you do not want to return any)
            references = [
                QueryReference(
                    link_on="automaticTag",  # the reference property
                    # properties from the referenced tags
                    return_properties=["uuid", "tag_name"]
                ),
                QueryReference(
                    link_on="positiveTag",
                    return_properties=["uuid", "tag_name"]
                ),
                QueryReference(
                    link_on="negativeTag",
                    return_properties=["uuid", "tag_name"]
                ),
                QueryReference(
                    link_on="userCollection"
                ),
            ]
            # returns all properties (except blobs) and specified references
            response = await self.client.collections.get(self.collectionNames.chunks_collection_name).query.fetch_objects(
                return_references=references,
                filters=filters
            )
            if response.objects is None:
                return []
            return response.objects
        except WeaviateConnectionError as e:
            logging.error(f"Error: {str(e)}")
            raise WeaviateConnectError(str(e))
        except WeaviateInvalidInputError as e:
            logging.error(f"Error: {str(e)}")
            raise WeaviateDataValidationError(str(e))
        except WeaviateTimeoutError as e:
            logging.error(f"Error: {str(e)}")
            raise WeaviateLimitError(str(e))
        except WeaviateQueryError as e:
            logging.error(f"Error: {str(e)}")
            raise WeaviateOperationError(str(e))
        except (UnexpectedStatusCodeError, ResponseCannotBeDecodedError) as e:
            logging.error(f"Error: {str(e)}")
            raise WeaviateServerError(str(e))
        except Exception as e:
            # catch unexpected errors and wrap them
            logging.error(f"Unexpected error fetching chunks: {str(e)}")
            raise WeaviateServerError(str(e))
