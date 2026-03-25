import { api } from 'src/boot/axios'
import { ENDPOINTS } from 'src/constants/ednpoints'
import { Document, DocumentBrowseParams, DocumentBrowseResponse, Documents } from 'src/models/documents'

const DocumentsService = {
  getDocuments: async (collectionId?: string) => await api.get<Documents>(ENDPOINTS.DOCUMENTS, { params: { collection_id: collectionId } }),
  browseDocuments: async (params: DocumentBrowseParams) => await api.get<DocumentBrowseResponse>(`${ENDPOINTS.DOCUMENTS}/browse`, {
    params: {
      collection_id: params.collectionId,
      limit: params.limit,
      offset: params.offset,
      sort_by: params.sortBy,
      sort_desc: params.sortDesc,
      title: params.title,
      author: params.author,
      publisher: params.publisher,
      document_type: params.documentType
    }
  }),
  getDocumentById: async (documentId: string) => await api.get<Document>(`${ENDPOINTS.DOCUMENTS}/${documentId}`)
}

export default DocumentsService
