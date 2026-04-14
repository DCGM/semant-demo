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
from semant_demo.schema.tags import PostTag, Tag as TagSchema, PatchTag
from uuid import UUID

import logging


class Tag():
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames
        self.helpers = WeaviateHelpers(client, collectionNames)

    #######
    # API #
    #######
    async def create(self, collection_id: UUID, tag: PostTag) -> TagSchema:
        """
        Creates a new tag in a collection, or returns the existing one if the same tag already exists in the collection
        """
        
        usercollection_collection = self.client.collections.get(self.collectionNames.user_collection_name)
        user_collection = await usercollection_collection.query.fetch_object_by_id(collection_id)
        if user_collection is None:
            raise WeaviateOperationError(f"Collection with id {collection_id} does not exist")
            
        tag_collection = self.client.collections.get(self.collectionNames.tag_collection_name)

        filters = Filter.by_ref("userCollection").by_id().equal(collection_id)
        existing = await tag_collection.query.fetch_objects(
            filters=filters,
            limit=2000
        )
        
        for obj in existing.objects:
            props = obj.properties
            existing_examples = [str(item) for item in (props.get("tag_examples") or [])]
            if (
                props["tag_name"] == tag.name and
                props["tag_shorthand"] == tag.shorthand and
                props["tag_color"] == tag.color and
                props["tag_pictogram"] == tag.pictogram and
                props["tag_definition"] == tag.definition and
                set(existing_examples) == set(tag.examples)
            ):
                # tag already exists, return it
                return TagSchema(
                    id=obj.uuid,
                    name=props["tag_name"],
                    shorthand=props["tag_shorthand"],
                    color=props["tag_color"],
                    pictogram=props["tag_pictogram"],
                    definition=props["tag_definition"],
                    examples=props["tag_examples"]
                )
        
        # create tag
        new_tag_uuid = await tag_collection.data.insert(
            properties={
                "tag_name": tag.name,
                "tag_shorthand": tag.shorthand,
                "tag_color": tag.color,
                "tag_pictogram": tag.pictogram,
                "tag_definition": tag.definition,
                "tag_examples": tag.examples
            }
        )
        
        await tag_collection.data.reference_add(
            from_uuid=new_tag_uuid,
            from_property="userCollection",
            to=collection_id
        )
        
        return TagSchema(
            name=tag.name,
            shorthand=tag.shorthand,
            color=tag.color,
            pictogram=tag.pictogram,
            definition=tag.definition,
            examples=tag.examples,
            id=new_tag_uuid,
        )

    async def read_all(self):
        """
        Retrieves all tags in the database with their collection names.
        """
        
        results = await self.helpers.fetch_tags()
        response = []
        # format the response
        for result in results:
            print(result)
            props = result.properties
            response.append({
                "tag_name": props["tag_name"],
                "tag_shorthand": props["tag_shorthand"],
                "tag_color": props["tag_color"],
                "tag_pictogram": props["tag_pictogram"],
                "tag_definition": props["tag_definition"],
                "tag_examples": props["tag_examples"],
                "collection_name": props.get("collection_name") or "",
                "tag_uuid": str(result.uuid)
            })

        return response
    
    async def read(self, tag_uuid: UUID) -> TagSchema | None:
        """
        Retrieves a tag by its UUID.
        """
        
        tag_collection = self.client.collections.get(self.collectionNames.tag_collection_name)
        response = await tag_collection.query.fetch_object_by_id(tag_uuid)
        if response is None:
            return None
        props = response.properties
        return TagSchema(
            id=response.uuid,
            name=props["tag_name"],
            shorthand=props["tag_shorthand"],
            color=props["tag_color"],
            pictogram=props["tag_pictogram"],
            definition=props["tag_definition"],
            examples=props["tag_examples"]
        )

    async def update(self, tag_uuid: UUID, updated_tag: PatchTag) -> TagSchema:
        """
        Updates an existing tag in a collection.
        """
        tag_collection = self.client.collections.get(self.collectionNames.tag_collection_name)

        tag_response = await tag_collection.query.fetch_object_by_id(
            tag_uuid,
        )
        if tag_response is None:
            raise WeaviateOperationError("Tag not found")

        patch_data = updated_tag.model_dump(exclude_unset=True, exclude_none=True)
        if not patch_data:
            raise WeaviateOperationError("No fields provided for update")

        properties_to_update: dict[str, str | list[str]] = {}

        if "name" in patch_data:
            properties_to_update["tag_name"] = str(patch_data["name"])
        if "shorthand" in patch_data:
            properties_to_update["tag_shorthand"] = str(patch_data["shorthand"])
        if "color" in patch_data:
            properties_to_update["tag_color"] = str(patch_data["color"])
        if "pictogram" in patch_data:
            properties_to_update["tag_pictogram"] = str(patch_data["pictogram"])
        if "definition" in patch_data:
            properties_to_update["tag_definition"] = str(patch_data["definition"])
        if "examples" in patch_data:
            properties_to_update["tag_examples"] = [
                str(example) for example in patch_data["examples"] if str(example).strip()
            ]

        await tag_collection.data.update(
            uuid=tag_uuid,
            properties=properties_to_update,
        )
        
        updated_tag = await self.read(tag_uuid)
        if updated_tag is None:
            raise WeaviateOperationError("Weaviate error: tag not found after update")

        return updated_tag

    # async def delete(self, chosenTagUUIDs):
    #     return await self.helpers.remove_tags(chosenTagUUIDs)

    async def delete(self, tag_uuid: UUID) -> None:
        """
        Deletes a tag after removing every reference to it from Span and Chunk collections.
        """
        tag_collection = self.client.collections.get(self.collectionNames.tag_collection_name)

        tag_response = await tag_collection.query.fetch_object_by_id(
            tag_uuid,
        )
        if tag_response is None:
            raise WeaviateOperationError("Tag not found")

        await self.helpers.delete_tag_with_references(str(tag_uuid))

    def read_spans():
        pass

    def search_spans():
        pass

    ###########
    # Helpers #
    ###########
