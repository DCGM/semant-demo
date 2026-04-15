import { useApi } from 'src/composables/useApi'
import { Tag, PostTag, Tags, PatchTag } from 'src/models/tags'

export function useTagsRepository() {
  const api = useApi().default

  return {
    getAllByCollection: async (collectionId: string): Promise<Tags> => {
      return api.getCollectionTagsApiCollectionsCollectionIdTagsGet({ collectionId })
    },
    getById: async (tagUuid: string): Promise<Tag> => {
      return api.getTagApiTagsTagUuidGet({ tagUuid })
    },
    create: async (collectionId: string, payload: PostTag): Promise<Tag> => {
      return api.createTagApiTagsPost({
        postTag: payload,
        collectionId
      })
    },
    delete: async (tagUuid: string): Promise<void> => {
      return api.deleteTagApiTagsTagUuidDelete({ tagUuid })
    },
    update: async (tagUuid: string, payload: PatchTag): Promise<Tag> => {
      return api.updateTagApiTagsTagUuidPatch({
        tagUuid,
        patchTag: payload
      })
    }
  }
}
