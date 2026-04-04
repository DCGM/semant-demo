import { DocumentBrowseParams } from 'src/models/documents'
import { useDocumentsStore } from 'src/stores/documentsStore'
import { computed } from 'vue'

const useDocuments = () => {
  const documentsStore = useDocumentsStore()

  const loadDocuments = (collectionId?: string) => documentsStore.fetchDocuments(collectionId)
  const loadDocument = (documentId: string) => documentsStore.fetchDocument(documentId)
  const browseDocuments = (params: DocumentBrowseParams) => documentsStore.browseDocuments(params)
  const addDoc = (documentId: string, collectionId: string) => documentsStore.addToCollection(documentId, collectionId)
  const removeDoc = (documentId: string, collectionId: string) => documentsStore.removeFromCollection(documentId, collectionId)
  const removeManyDocs = (documentIds: string[], collectionId: string) => documentsStore.removeManyFromCollection(documentIds, collectionId)

  const documents = computed(() => documentsStore.documents)
  const activeDocument = computed(() => documentsStore.activeDocument)
  const loading = computed(() => documentsStore.loading)
  const error = computed(() => documentsStore.error)

  return {
    loadDocuments,
    loadDocument,
    browseDocuments,
    addDoc,
    removeDoc,
    removeManyDocs,

    documents,
    activeDocument,
    loading,
    error
  }
}

export default useDocuments
