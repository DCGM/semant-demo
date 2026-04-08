import type { SemantDemoSchemaDocumentsDocument, DocumentBrowse } from 'src/generated/api'

type Document = SemantDemoSchemaDocumentsDocument
type Documents = Document[]
type DocumentBrowseParams = {
  collectionId?: string
  limit: number
  offset: number
  sortBy?: string
  sortDesc?: boolean
  title?: string
  author?: string
  publisher?: string
  documentType?: string
}

export type { Document, Documents, DocumentBrowse, DocumentBrowseParams }
