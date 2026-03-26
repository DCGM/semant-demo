import { Document, DocumentBrowseParams, DocumentBrowseResponse, Documents } from 'src/models/documents'
import {
  DocumentBrowseParamsSchema,
  DocumentBrowseResponseSchema,
  DocumentSchema,
  DocumentsSchema
} from 'src/schemas/documents'
import DocumentsService from 'src/services/DocumentsService'

const DocumentsRepository = {
  getAll: async (collectionId?: string): Promise<Documents> => {
    const response = await DocumentsService.getDocuments(collectionId)
    const data = response.data

    const parsedData = DocumentsSchema.safeParse(data)

    if (!parsedData.success) {
      throw new Error('Failed to parse documents data from API')
    }

    return parsedData.data
  },

  getById: async (documentId: string): Promise<Document> => {
    const response = await DocumentsService.getDocumentById(documentId)
    const data = response.data

    const parsedData = DocumentSchema.safeParse(data)

    if (!parsedData.success) {
      throw new Error('Failed to parse document data from API')
    }

    return parsedData.data
  },

  browse: async (params: DocumentBrowseParams): Promise<DocumentBrowseResponse> => {
    const parsedParams = DocumentBrowseParamsSchema.safeParse(params)
    if (!parsedParams.success) {
      throw new Error('Invalid browse params')
    }

    const response = await DocumentsService.browseDocuments(parsedParams.data)
    const data = response.data

    console.log('Raw browse response data:', data)
    const parsedData = DocumentBrowseResponseSchema.safeParse(data)
    if (!parsedData.success) {
      throw new Error(`Failed to parse browsed documents data from API: ${parsedData.error.message}`)
    }

    return parsedData.data
  },

  addToCollection: async (documentId: string, collectionId: string): Promise<boolean> => {
    const response = await DocumentsService.addDocumentToCollection(documentId, collectionId)
    return response.data.success
  }
}

export default DocumentsRepository
