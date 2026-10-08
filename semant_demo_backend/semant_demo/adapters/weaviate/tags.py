"""Tag definitions. Each tag belongs to one user collection."""
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter, QueryReference

import semant_demo.schemas as schemas
from semant_demo.adapters.weaviate.paging import fetch_all
from semant_demo.adapters.weaviate.writes import delete_tag_cascade
from semant_demo.core.errors import InvalidRequestError, NotFoundError
from semant_demo.features.annotations.schemas import PatchTag, PostTag, Tag

# Request field -> stored property.
_PROPERTIES = {
    "name": "tag_name",
    "shorthand": "tag_shorthand",
    "color": "tag_color",
    "pictogram": "tag_pictogram",
    "definition": "tag_definition",
    "examples": "tag_examples",
}


def to_tag(obj) -> Tag:
    props = obj.properties
    return Tag(
        id=obj.uuid,
        name=props["tag_name"],
        shorthand=props["tag_shorthand"],
        color=props["tag_color"],
        pictogram=props["tag_pictogram"],
        definition=props["tag_definition"],
        examples=props.get("tag_examples") or [],
    )


class TagRepository:
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames

    def _tags(self):
        return self.client.collections.get(self.collectionNames.tag_collection_name)

    async def find_same(self, collection_id: UUID, tag: PostTag) -> Tag | None:
        """
        A tag of the collection with exactly the same fields (examples in any order), or
        None. Raises ``NotFoundError`` if the collection does not exist.

        Reads at most 2000 tags of the collection (#218).
        """
        collections = self.client.collections.get(self.collectionNames.user_collection_name)
        if await collections.query.fetch_object_by_id(collection_id, return_properties=[]) is None:
            raise NotFoundError("Collection not found")
        existing = await self._tags().query.fetch_objects(
            filters=Filter.by_ref("userCollection").by_id().equal(collection_id),
            limit=2000,
        )
        for obj in existing.objects:
            found = to_tag(obj)
            if (found.name, found.shorthand, found.color, found.pictogram, found.definition) == (
                    tag.name, tag.shorthand, tag.color, tag.pictogram, tag.definition
            ) and set(found.examples) == set(tag.examples):
                return found
        return None

    async def insert(self, tag: PostTag) -> UUID:
        """Stores the tag without a collection (see ``link_to_collection``) and returns its id."""
        return await self._tags().data.insert(
            properties={_PROPERTIES[field]: value for field, value in tag.model_dump().items()})

    async def link_to_collection(self, tag_id: UUID, collection_id: UUID) -> None:
        await self._tags().data.reference_add(from_uuid=tag_id, from_property="userCollection", to=collection_id)

    async def delete_unlinked(self, tag_id: UUID) -> None:
        """Deletes a tag that was just inserted; it has no spans or chunk tag references yet."""
        await self._tags().data.delete_by_id(tag_id)

    async def read(self, tag_id: UUID) -> Tag | None:
        """The tag with this id, or None if it does not exist."""
        response = await self._tags().query.fetch_object_by_id(tag_id)
        return to_tag(response) if response is not None else None

    async def read_by_collection(self, collection_id: UUID) -> list[Tag]:
        """All tags of the collection."""
        objects = await fetch_all(self._tags(), filters=Filter.by_ref("userCollection").by_id().equal(collection_id))
        return [to_tag(obj) for obj in objects]

    async def read_collection_ids(self, tag_ids: list[UUID]) -> dict[UUID, list[UUID]]:
        """
        The collections each existing tag references. Tags that do not exist are absent
        from the result. Used for authorization.
        """
        if not tag_ids:
            return {}
        response = await self._tags().query.fetch_objects(
            filters=Filter.by_id().contains_any(list(tag_ids)),
            limit=len(tag_ids),
            return_properties=[],
            return_references=[QueryReference(link_on="userCollection")],
        )
        result: dict[UUID, list[UUID]] = {}
        for obj in response.objects:
            refs = obj.references.get("userCollection") if obj.references else None
            result[obj.uuid] = [r.uuid for r in (refs.objects if refs else [])]
        return result

    async def update(self, tag_id: UUID, patch: PatchTag) -> Tag:
        """
        Sets the fields given with a value; fields omitted or null are kept. Empty or
        blank examples are dropped. Raises ``NotFoundError`` if the tag does not exist.
        """
        tags = self._tags()
        if await tags.query.fetch_object_by_id(tag_id, return_properties=[]) is None:
            raise NotFoundError("Tag not found")

        patch_data = patch.model_dump(exclude_unset=True, exclude_none=True)
        if not patch_data:
            raise InvalidRequestError("No fields provided for update")
        if "examples" in patch_data:
            patch_data["examples"] = [example for example in patch_data["examples"] if example.strip()]

        await tags.data.update(
            uuid=tag_id,
            properties={_PROPERTIES[field]: value for field, value in patch_data.items()},
        )
        updated = await self.read(tag_id)
        if updated is None:
            raise NotFoundError("Tag not found")
        return updated

    async def delete(self, tag_id: UUID) -> None:
        """
        Deletes the tag after its chunk tag references and spans. Raises ``NotFoundError``
        if the tag does not exist and ``IncompleteWriteError`` if a step fails.
        """
        if await self._tags().query.fetch_object_by_id(tag_id, return_properties=[]) is None:
            raise NotFoundError("Tag not found")
        await delete_tag_cascade(self.client, self.collectionNames, tag_id)
