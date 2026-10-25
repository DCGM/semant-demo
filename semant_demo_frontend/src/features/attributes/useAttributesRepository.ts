import { useApi } from 'src/shared/api'
import type { Attribute, PatchAttribute, PatchAttributeValue, PostAttribute, PostAttributeValue } from 'src/generated/api'

/** The attribute definition routes of a collection (#331, ADR 0011). */
export function useAttributesRepository () {
  const api = useApi().default

  return {
    getAll: (collectionId: string): Promise<Attribute[]> =>
      api.listAttributesApiUserCollectionsCollectionIdAttributesGet({ collectionId }),
    create: (collectionId: string, postAttribute: PostAttribute): Promise<Attribute> =>
      api.createAttributeApiUserCollectionsCollectionIdAttributesPost({ collectionId, postAttribute }),
    update: (collectionId: string, attributeId: string, patchAttribute: PatchAttribute): Promise<Attribute> =>
      api.updateAttributeApiUserCollectionsCollectionIdAttributesAttributeIdPatch({ collectionId, attributeId, patchAttribute }),
    delete: (collectionId: string, attributeId: string): Promise<void> =>
      api.deleteAttributeApiUserCollectionsCollectionIdAttributesAttributeIdDelete({ collectionId, attributeId }),
    addValue: (collectionId: string, attributeId: string, postAttributeValue: PostAttributeValue): Promise<Attribute> =>
      api.addAttributeValueApiUserCollectionsCollectionIdAttributesAttributeIdValuesPost({
        collectionId, attributeId, postAttributeValue
      }),
    updateValue: (collectionId: string, attributeId: string, valueId: string,
      patchAttributeValue: PatchAttributeValue): Promise<Attribute> =>
      api.updateAttributeValueApiUserCollectionsCollectionIdAttributesAttributeIdValuesValueIdPatch({
        collectionId, attributeId, valueId, patchAttributeValue
      }),
    deleteValue: (collectionId: string, attributeId: string, valueId: string): Promise<Attribute> =>
      api.deleteAttributeValueApiUserCollectionsCollectionIdAttributesAttributeIdValuesValueIdDelete({
        collectionId, attributeId, valueId
      })
  }
}
