import { Tag, TagCreate, Tags } from 'src/models/tags'
import { TagCreateSchema, TagSchema, TagsSchema } from 'src/schemas/tags'
import TagsService from 'src/services/TagsService'

const TagsRepository = {
  getByCollection: async (collectionId: string): Promise<Tags> => {
    const response = await TagsService.getCollectionTags(collectionId)
    const parsedData = TagsSchema.safeParse(response.data)

    if (!parsedData.success) {
      throw new Error('Failed to parse collection tags data from API')
    }

    return parsedData.data
  },

  createInCollection: async (collectionId: string, payload: TagCreate): Promise<Tag> => {
    const parsedPayload = TagCreateSchema.safeParse(payload)
    if (!parsedPayload.success) {
      throw new Error('Invalid tag payload')
    }

    const response = await TagsService.createCollectionTag(collectionId, parsedPayload.data)
    const parsedData = TagSchema.safeParse(response.data)

    if (!parsedData.success) {
      throw new Error('Failed to parse created tag data from API')
    }

    return parsedData.data
  }
}

export default TagsRepository
