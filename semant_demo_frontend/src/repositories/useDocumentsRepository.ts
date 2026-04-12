import { useApi } from 'src/composables/useApi'
import { Document, DocumentBrowseParams, DocumentBrowse, Documents } from 'src/models/documents'

export function useDocumentsRepository() {
  const api = useApi().default

  return {
    getAllByCollection: async (collectionId: string): Promise<Documents> => {
      return api.getCollectionDocumentsApiUserCollectionCollectionIdDocumentsGet({ collectionId })
    },

    getById: async (documentId: string): Promise<Document> => {
      return api.fetchDocumentApiDocumentDocumentIdGet({ documentId })
    },

    browse: async (params: DocumentBrowseParams): Promise<DocumentBrowse> => {
      return api.browseDocumentsApiDocumentsBrowseGet(params)
    },

    addToCollection: async (documentId: string, collectionId: string): Promise<void> => {
      return await api.addDocumentToCollectionApiCollectionsCollectionIdDocumentsDocumentIdPost({ collectionId, documentId })
    },

    removeFromCollection: async (documentId: string, collectionId: string): Promise<void> => {
      return await api.removeDocumentFromCollectionApiCollectionsCollectionIdDocumentsDocumentIdDelete({ collectionId, documentId })
    }
  }
}
