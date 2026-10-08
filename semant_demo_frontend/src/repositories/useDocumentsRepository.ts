import { useApi } from 'src/shared/api'
import { Document, DocumentBrowseParams, DocumentBrowse, Documents } from 'src/models/documents'
import { DocumentStats, WriteResult } from 'src/generated/api'
import { requireComplete } from 'src/utils/writeOutcome'

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

    /** Throws IncompleteWriteError when some chunk/document links could not be written. */
    addToCollection: async (documentId: string, collectionId: string): Promise<WriteResult> => {
      return requireComplete(
        await api.addDocumentToCollectionApiCollectionsCollectionIdDocumentsDocumentIdPost({ collectionId, documentId }),
        'Adding the document'
      )
    },

    /** Throws IncompleteWriteError when some links could not be removed (the document then stays). */
    removeFromCollection: async (documentId: string, collectionId: string): Promise<WriteResult> => {
      return requireComplete(
        await api.removeDocumentFromCollectionApiCollectionsCollectionIdDocumentsDocumentIdDelete({ collectionId, documentId }),
        'Removing the document'
      )
    },

    getStats: async (collectionId: string, documentId: string): Promise<DocumentStats> => {
      return api.getDocumentStatsApiCollectionsCollectionIdDocumentsDocumentIdStatsGet({ collectionId, documentId })
    }
  }
}
