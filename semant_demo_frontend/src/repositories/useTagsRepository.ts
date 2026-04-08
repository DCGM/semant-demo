import { useApi } from 'src/composables/useApi'
import { PatchTag } from 'src/generated/api'
import { Tag, PostTag, Tags } from 'src/models/tags'

export function useTagsRepository() {
  const api = useApi().default

  return {
    getByCollection: async (collectionId: string): Promise<Tags> => {
      return api.getCollectionTagsApiV1CollectionsCollectionIdTagsGet({ collectionId })
    },
    createInCollection: async (collectionId: string, payload: PostTag): Promise<Tag> => {
      return api.createCollectionTagApiV1CollectionsCollectionIdTagsPost({
        collectionId,
        postTag: payload
      })
    },
    deleteFromCollection: async (collectionId: string, tagUuid: string): Promise<void> => {
      return api.deleteCollectionTagApiV1CollectionsCollectionIdTagsTagUuidDelete({
        collectionId,
        tagUuid
      })
    },
    updateInCollection: async (collectionId: string, tagUuid: string, payload: PatchTag): Promise<Tag> => {
      return api.updateCollectionTagApiV1CollectionsCollectionIdTagsTagUuidPatch({
        collectionId,
        tagUuid,
        patchTag: payload
      })
    }
  }
}
