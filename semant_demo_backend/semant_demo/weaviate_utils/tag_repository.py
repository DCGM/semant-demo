from uuid import UUID

from weaviate.classes.query import Filter

import semant_demo.schemas as schemas
from semant_demo.weaviate_exceptions import NotFoundError
from semant_demo.weaviate_utils.base_repository import WeaviateBaseRepository
from semant_demo.schema.tags import PostTag, Tag as TagSchema, PatchTag


class TagRepository(WeaviateBaseRepository):
    """Repository for the Weaviate tag collection."""

    async def create(self, collection_id: UUID, tag: PostTag) -> TagSchema:
        """
        Creates a new tag in a user collection, or returns the existing one if
        an identical tag (same name/shorthand/color/pictogram/definition/examples)
        already exists in that collection.

        Args:
            collection_id: UUID of the user collection the tag belongs to.
            tag: tag data to create.

        Returns:
            The created (or matching existing) tag.

        Raises:
            NotFoundError: the given collection_id does not exist.
        """
        usercollection_collection = self.client.collections.get(self.collectionNames.user_collection_name)
        user_collection = await usercollection_collection.query.fetch_object_by_id(collection_id)
        if user_collection is None:
            raise NotFoundError(f"Collection with id {collection_id} does not exist")

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

    async def read(self, tag_uuid: UUID) -> TagSchema | None:
        """
        Retrieves a tag by its UUID.

        Args:
            tag_uuid: UUID of the tag.

        Returns:
            The tag, or None if no tag with this id exists.
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

    async def read_all(self) -> list[schemas.TagData]:
        """
        Retrieves all tags in the database with their collection names.

        Returns:
            All tags, each annotated with the name of the collection it belongs to.
        """
        results = await self.helpers.fetch_tags()
        return [
            schemas.TagData(
                tag_name=result.properties["tag_name"],
                tag_shorthand=result.properties["tag_shorthand"],
                tag_color=result.properties["tag_color"],
                tag_pictogram=result.properties["tag_pictogram"],
                tag_definition=result.properties["tag_definition"],
                tag_examples=result.properties["tag_examples"],
                collection_name=result.properties.get("collection_name") or "",
                tag_uuid=result.uuid,
            )
            for result in results
        ]

    async def update(self, tag_uuid: UUID, updated_tag: PatchTag) -> TagSchema:
        """
        Applies a partial update to an existing tag. PatchTag guarantees at
        least one field is set (see schema/tags.py), so an empty patch never
        reaches this method.

        Args:
            tag_uuid: UUID of the tag to update.
            updated_tag: fields to change; unset fields are left untouched.

        Returns:
            The updated tag.

        Raises:
            NotFoundError: no tag with this id exists.
        """
        tag_collection = self.client.collections.get(self.collectionNames.tag_collection_name)

        tag_response = await tag_collection.query.fetch_object_by_id(tag_uuid)
        if tag_response is None:
            raise NotFoundError(f"Tag with id {tag_uuid} not found")

        patch_data = updated_tag.model_dump(exclude_unset=True, exclude_none=True)

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

        updated = await self.read(tag_uuid)
        if updated is None:
            raise NotFoundError(f"Tag with id {tag_uuid} not found after update")
        return updated

    async def delete(self, tag_uuid: str) -> None:
        """
        Deletes a tag after removing every reference to it from Span and Chunk collections.

        Args:
            tag_uuid: UUID of the tag to delete.

        Raises:
            NotFoundError: no tag with this id exists.
        """
        tag_collection = self.client.collections.get(self.collectionNames.tag_collection_name)

        tag_response = await tag_collection.query.fetch_object_by_id(tag_uuid)
        if tag_response is None:
            raise NotFoundError(f"Tag with id {tag_uuid} not found")

        await self.helpers.delete_tag_cascade(tag_uuid)
