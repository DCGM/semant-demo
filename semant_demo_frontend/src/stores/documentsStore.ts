import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { Documents, Document, DocumentBrowseParams } from 'src/models/documents'
import { ongoingNotification } from 'src/utils/notification'
import { useDocumentsRepository } from 'src/repositories/useDocumentsRepository'

export const useDocumentsStore = defineStore('documents', () => {
  const documentsRepository = useDocumentsRepository()
  const documents = ref<Documents>([])
  const activeDocument = ref<Document | null>(null)
  const error = ref<string | null>(null)
  const loading = ref<boolean>(false)
  const pendingRemoveIds = ref<Set<string>>(new Set())

  const visibleDocuments = computed(() =>
    documents.value.filter((doc) => !pendingRemoveIds.value.has(doc.id))
  )

  const fetchDocumentsByCollection = async (collectionId: string) => {
    // const notif = ongoingNotification('Loading documents...')
    loading.value = true
    error.value = null
    try {
      const data = await documentsRepository.getAllByCollection(collectionId)
      documents.value = data
      // notif.success('Documents loaded')
    } catch (err) {
      error.value = 'Failed to fetch documents'
      console.error('Error fetching documents:', err)
      // notif.error('Failed to load documents')
    } finally {
      loading.value = false
    }
  }

  const fetchDocument = async (documentId: string) => {
    // const notif = ongoingNotification('Loading document...')
    loading.value = true
    error.value = null
    try {
      const data = await documentsRepository.getById(documentId)
      activeDocument.value = data
      // notif.success('Document loaded')
    } catch (err) {
      error.value = 'Failed to fetch document'
      console.error('Error fetching document:', err)
      // notif.error('Failed to load document')
    } finally {
      loading.value = false
    }
  }
  const browseDocuments = async (params: DocumentBrowseParams) => {
    // const notif = ongoingNotification('Browsing documents...')
    loading.value = true
    error.value = null
    try {
      const data = await documentsRepository.browse(params)
      documents.value = data.items
      // notif.success('Documents loaded')
      return data
    } catch (err) {
      error.value = 'Failed to browse documents'
      console.error('Error browsing documents:', err)
      // notif.error('Failed to load documents')
      throw err
    } finally {
      loading.value = false
    }
  }

  const addToCollection = async (documentId: string, collectionId: string) => {
    const notif = ongoingNotification('Adding document to collection...')
    error.value = null
    loading.value = true
    try {
      await documentsRepository.addToCollection(documentId, collectionId)
      await fetchDocumentsByCollection(collectionId)
      notif.success('Document added to collection')
    } catch (err) {
      error.value = 'Failed to add document to collection'
      console.error('Error adding document to collection:', err)
      notif.error('Failed to add document to collection')
      return false
    } finally {
      loading.value = false
    }
  }

  const removeFromCollection = async (documentId: string, collectionId: string) => {
    const notif = ongoingNotification('Removing document from collection...')
    error.value = null
    loading.value = true
    try {
      await documentsRepository.removeFromCollection(documentId, collectionId)
      await fetchDocumentsByCollection(collectionId)
      notif.success('Document removed from collection')
    } catch (err) {
      error.value = 'Failed to remove document from collection'
      console.error('Error removing document from collection:', err)
      notif.error('Failed to remove document from collection')
      return false
    } finally {
      loading.value = false
    }
  }

  const removeManyFromCollection = async (documentIds: string[], collectionId: string) => {
    if (documentIds.length === 0) return

    const notif = ongoingNotification('Removing selected documents from collection...')
    documentIds.forEach((id) => pendingRemoveIds.value.add(id))
    documents.value = documents.value.filter((doc) => !documentIds.includes(doc.id))
    error.value = null
    let hadError = false
    try {
      await Promise.all(
        documentIds.map((documentId) => documentsRepository.removeFromCollection(documentId, collectionId))
      )
      notif.success('Selected documents removed from collection')
    } catch (err) {
      hadError = true
      error.value = 'Failed to remove selected documents from collection'
      console.error('Error removing selected documents from collection:', err)
      notif.error('Failed to remove selected documents from collection')
      await fetchDocumentsByCollection(collectionId)
    } finally {
      if (!hadError) {
        documents.value = documents.value.filter((doc) => !documentIds.includes(doc.id))
      }
      documentIds.forEach((id) => pendingRemoveIds.value.delete(id))
    }
  }

  return {
    documents: visibleDocuments,
    activeDocument,
    error,
    loading,

    fetchDocument,
    fetchDocumentsByCollection,
    browseDocuments,
    addToCollection,
    removeFromCollection,
    removeManyFromCollection
  }
})
