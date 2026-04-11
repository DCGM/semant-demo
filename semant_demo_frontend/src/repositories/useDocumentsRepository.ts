import { useApi } from 'src/composables/useApi'
import { Document, DocumentBrowseParams, DocumentBrowse, Documents } from 'src/models/documents'

export function useDocumentsRepository() {
  const api = useApi().default

  return {
    getAll: async (collectionId?: string): Promise<Documents> => {
      return api.getDocumentsApiV1DocumentsGet({ collectionId }) // TODO: change in the future - shouldn't be filtered by collectionID
    },

    getAllByCollection: async (collectionId: string): Promise<Documents> => {
      return api.getCollectionDocumentsApiUserCollectionCollectionIdDocumentsGet({ collectionId })
    },

    getById: async (documentId: string): Promise<Document> => {
      return api.getDocumentApiV1DocumentsDocumentIdGet({ documentId })
    },

    browse: async (params: DocumentBrowseParams): Promise<DocumentBrowse> => {
      return api.browseDocumentsApiDocumentsBrowseGet(params)
    },

    addToCollection: async (documentId: string, collectionId: string): Promise<boolean> => {
      const response = await api.addDocumentToCollectionApiV1CollectionsCollectionIdDocumentsDocumentIdPost({ collectionId, documentId })
      return response.success
    },

    removeFromCollection: async (documentId: string, collectionId: string): Promise<boolean> => {
      const response = await api.removeDocumentFromCollectionApiV1CollectionsCollectionIdDocumentsDocumentIdDelete({ collectionId, documentId })
      return response.success
    }
  }
}
