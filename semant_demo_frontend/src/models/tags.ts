import { z } from 'zod'

import { TagCreateSchema, TagSchema, TagsSchema } from 'src/schemas/tags'

export type Tag = z.infer<typeof TagSchema>
export type Tags = z.infer<typeof TagsSchema>
export type TagCreate = z.infer<typeof TagCreateSchema>
