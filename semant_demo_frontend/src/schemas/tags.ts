import { z } from 'zod'

const TagSchema = z.object({
  tagName: z.string(),
  tagShorthand: z.string(),
  tagColor: z.string(),
  tagPictogram: z.string(),
  tagDefinition: z.string().optional(),
  tagExamples: z.array(z.string()).optional(),
  tagUuid: z.uuid()
})

const TagsSchema = z.array(TagSchema)

const TagCreateSchema = z.object({
  tagName: z.string(),
  tagShorthand: z.string(),
  tagColor: z.string(),
  tagPictogram: z.string(),
  tagDefinition: z.string().optional(),
  tagExamples: z.array(z.string()).optional()
})

export { TagSchema, TagsSchema, TagCreateSchema }
