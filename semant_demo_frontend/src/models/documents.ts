import { z } from 'zod'

import { DocumentBrowseParamsSchema, DocumentBrowseResponseSchema, DocumentSchema, DocumentsSchema } from 'src/schemas/documents'

export type Document = z.infer<typeof DocumentSchema>
export type Documents = z.infer<typeof DocumentsSchema>
export type DocumentBrowseParams = z.infer<typeof DocumentBrowseParamsSchema>
export type DocumentBrowseResponse = z.infer<typeof DocumentBrowseResponseSchema>
