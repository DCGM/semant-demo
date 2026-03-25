import { defineStore } from 'pinia'
import { ref } from 'vue'
import { Documents, Document } from 'src/models/documents'
import { ongoingNotification } from 'src/utils/notification'
import DocumentsRepository from 'src/repositories/DocumentsRepository'

export const useDocumentsStore = defineStore('documents', () => {
  const documents = ref<Documents>([])
  const activeDocument = ref<Document | null>(null)
  const error = ref<string | null>(null)
  const loading = ref<boolean>(false)

  const fetchDocuments = async (collectionId?: string) => {
    const notif = ongoingNotification('Loading documents...')
    loading.value = true
    error.value = null
    try {
      const data = await DocumentsRepository.getAll(collectionId)
      documents.value = data
      notif.success('Documents loaded')
    } catch (err) {
      error.value = 'Failed to fetch documents'
      console.error('Error fetching documents:', err)
      notif.error('Failed to load documents')
    } finally {
      loading.value = false
    }
  }
  const fetchDocument = async (documentId: string) => {
    const notif = ongoingNotification('Loading document...')
    loading.value = true
    error.value = null
    try {
      const data = await DocumentsRepository.getById(documentId)
      activeDocument.value = data
      notif.success('Document loaded')
    } catch (err) {
      error.value = 'Failed to fetch document'
      console.error('Error fetching document:', err)
      notif.error('Failed to load document')
    } finally {
      loading.value = false
    }
  }

  return {
    documents,
    activeDocument,
    error,
    loading,

    fetchDocuments,
    fetchDocument
  }
})
