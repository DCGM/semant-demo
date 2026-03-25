import { useDocumentsStore } from 'src/stores/documents_store'
import { computed } from 'vue'

const useDocuments = () => {
  const documentsStore = useDocumentsStore()

  const loadDocuments = (collectionId?: string) => documentsStore.fetchDocuments(collectionId)
  const loadDocument = (documentId: string) => documentsStore.fetchDocument(documentId)

  const documents = computed(() => documentsStore.documents)
  const activeDocument = computed(() => documentsStore.activeDocument)
  const loading = computed(() => documentsStore.loading)
  const error = computed(() => documentsStore.error)

  return {
    loadDocuments,
    loadDocument,

    documents,
    activeDocument,
    loading,
    error
  }
}

export default useDocuments
