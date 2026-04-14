import { z } from 'zod'

const DocumentSchema = z.object({
  id: z.string(),

  title: z.string().optional(),
  public: z.boolean().optional(),
  documentType: z.string().optional(),
  partNumber: z.string().optional(),
  dateIssued: z.iso.datetime().optional().transform((date) => date ? new Date(date) : undefined),
  yearIssued: z.number().optional(),
  language: z.string().optional(),
  publisher: z.string().optional(),
  placeOfPublication: z.string().optional(),
  subtitle: z.string().optional(),
  editors: z.array(z.string()).optional(),
  partName: z.string().optional(),
  seriesName: z.string().optional(),
  edition: z.string().optional(),
  author: z.array(z.string()).optional(),
  illustrators: z.array(z.string()).optional(),
  translators: z.array(z.string()).optional(),
  redaktors: z.array(z.string()).optional(),
  series_number: z.string().optional(),
  keywords: z.array(z.string()).optional()
})

const DocumentsSchema = z.array(DocumentSchema)

const DocumentBrowseParamsSchema = z.object({
  collectionId: z.uuid().optional(),
  limit: z.number().int().positive(),
  offset: z.number().int().min(0),
  sortBy: z.string().optional(),
  sortDesc: z.boolean().optional(),
  title: z.string().optional(),
  author: z.string().optional(),
  publisher: z.string().optional(),
  documentType: z.string().optional()
})

const DocumentBrowseResponseSchema = z.object({
  items: DocumentsSchema,
  nextOffset: z.number().int().nullable().optional(),
  hasMore: z.boolean(),
  totalCount: z.number().int().min(0)
})

export {
  DocumentSchema,
  DocumentsSchema,
  DocumentBrowseParamsSchema,
  DocumentBrowseResponseSchema
}
