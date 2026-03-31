import { z } from 'zod'
import { CollectionSchema, CollectionsSchema, PostCollectionSchema, PatchCollectionSchema, CollectionStatsSchema } from 'src/schemas/collection'

export type Collection = z.infer<typeof CollectionSchema>
export type Collections = z.infer<typeof CollectionsSchema>
export type PostCollection = z.infer<typeof PostCollectionSchema>
export type PatchCollection = z.infer<typeof PatchCollectionSchema>
export type CollectionStats = z.infer<typeof CollectionStatsSchema>
