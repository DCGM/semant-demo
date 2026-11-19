import { useApi } from 'src/shared/api'
import { Document, DocumentBrowse, DocumentStats, TextUploadResponse, WriteResult } from 'src/generated/api'
import { requireComplete } from 'src/shared/writeOutcome'

export type DocumentBrowseParams = {
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

export function useDocumentsRepository() {
  const api = useApi().default

  return {
    getAllByCollection: async (collectionId: string): Promise<Document[]> => {
      return api.getCollectionDocumentsApiUserCollectionsCollectionIdDocumentsGet({ collectionId })
    },

    /** A public document, or one of `collectionId` whatever its rights (#279). */
    getById: async (documentId: string, collectionId: string | null = null): Promise<Document> => {
      return api.fetchDocumentApiDocumentDocumentIdGet({ documentId, collectionId })
    },

    browse: async (params: DocumentBrowseParams): Promise<DocumentBrowse> => {
      return api.browseDocumentsApiDocumentsBrowseGet(params)
    },

    /** Throws IncompleteWriteError when some chunk/document links could not be written. */
    addToCollection: async (documentId: string, collectionId: string): Promise<WriteResult> => {
      return requireComplete(
        await api.addDocumentToCollectionApiUserCollectionsCollectionIdDocumentsDocumentIdPost({ collectionId, documentId }),
        'Adding the document'
      )
    },

    /**
     * Uploads private text files into the collection (#785); the result of each file, also
     * when some or all were not saved. Rejects when the request itself fails.
     */
    uploadTextDocuments: async (collectionId: string, files: File[], metadata: File | null): Promise<TextUploadResponse> => {
      return api.uploadTextDocumentsApiUserCollectionsCollectionIdTextDocumentsPost({
        collectionId, files, metadata: metadata ?? undefined
      })
    },

    /** Throws IncompleteWriteError when some links could not be removed (the document then stays). */
    removeFromCollection: async (documentId: string, collectionId: string): Promise<WriteResult> => {
      return requireComplete(
        await api.removeDocumentFromCollectionApiUserCollectionsCollectionIdDocumentsDocumentIdDelete({ collectionId, documentId }),
        'Removing the document'
      )
    },

    getStats: async (collectionId: string, documentId: string): Promise<DocumentStats> => {
      return api.getDocumentStatsApiUserCollectionsCollectionIdDocumentsDocumentIdStatsGet({ collectionId, documentId })
    }
  }
}
