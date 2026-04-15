import { api } from 'src/boot/axios'
import { ENDPOINTS } from 'src/constants/endpoints'
import { Tag, TagCreate, Tags } from 'src/models/tags'

const TagsService = {
  getCollectionTags: async (collectionId: string) =>
    await api.get<Tags>(`${ENDPOINTS.COLLECTIONS}/${collectionId}/tags`),

  createCollectionTag: async (collectionId: string, payload: TagCreate) =>
    await api.post<Tag>(`${ENDPOINTS.COLLECTIONS}/${collectionId}/tags`, payload)
}

export default TagsService
