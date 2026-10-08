import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { Documents, Document, DocumentBrowseParams } from 'src/models/documents'
import { ongoingNotification } from 'src/utils/notification'
import { useDocumentsRepository } from 'src/repositories/useDocumentsRepository'
import { IncompleteWriteError } from 'src/utils/writeOutcome'
import { captureSession, createContextGuard } from 'src/shared/api'

export const useDocumentsStore = defineStore('documents', () => {
  const documentsRepository = useDocumentsRepository()
  const documents = ref<Documents>([])
  const activeDocument = ref<Document | null>(null)
  const error = ref<string | null>(null)
  const loading = ref<boolean>(false)
  const pendingRemoveIds = ref<Set<string>>(new Set())
  // Only the latest load sets the list / the open document (another collection or
  // document may be open by now).
  const listRequests = createContextGuard()
  const activeRequests = createContextGuard()

  const visibleDocuments = computed(() =>
    documents.value.filter((doc) => !pendingRemoveIds.value.has(doc.id))
  )

  let listCollectionId: string | null = null

  const fetchDocumentsByCollection = async (collectionId: string) => {
    listRequests.enter()
    const isCurrent = listRequests.capture()
    if (listCollectionId !== collectionId) documents.value = []
    listCollectionId = collectionId
    loading.value = true
    error.value = null
    try {
      const data = await documentsRepository.getAllByCollection(collectionId)
      if (isCurrent()) documents.value = data
    } catch (err) {
      if (!isCurrent()) return
      error.value = 'Failed to fetch documents'
      console.error('Error fetching documents:', err)
    } finally {
      if (isCurrent()) loading.value = false
    }
  }

  const fetchDocument = async (documentId: string) => {
    activeRequests.enter()
    const isCurrent = activeRequests.capture()
    if (activeDocument.value?.id !== documentId) activeDocument.value = null
    loading.value = true
    error.value = null
    try {
      const data = await documentsRepository.getById(documentId)
      if (isCurrent()) activeDocument.value = data
    } catch (err) {
      if (!isCurrent()) return
      error.value = 'Failed to fetch document'
      console.error('Error fetching document:', err)
    } finally {
      if (isCurrent()) loading.value = false
    }
  }
  const browseDocuments = async (params: DocumentBrowseParams) => {
    listRequests.enter()
    const isCurrent = listRequests.capture()
    listCollectionId = null
    loading.value = true
    error.value = null
    try {
      const data = await documentsRepository.browse(params)
      if (isCurrent()) documents.value = data.items
      return data
    } catch (err) {
      if (isCurrent()) {
        error.value = 'Failed to browse documents'
        console.error('Error browsing documents:', err)
      }
      throw err
    } finally {
      if (isCurrent()) loading.value = false
    }
  }

  /** Drops the documents (logout). */
  const clear = () => {
    listRequests.enter()
    activeRequests.enter()
    listCollectionId = null
    documents.value = []
    activeDocument.value = null
    error.value = null
    loading.value = false
  }

  const addToCollection = async (documentId: string, collectionId: string) => {
    const notif = ongoingNotification('Adding document to collection...')
    const inSession = captureSession()
    error.value = null
    loading.value = true
    try {
      await documentsRepository.addToCollection(documentId, collectionId)
      if (!inSession()) {
        notif.dismiss()
        return true
      }
      await fetchDocumentsByCollection(collectionId)
      notif.success('Document added to collection')
      return true
    } catch (err) {
      if (!inSession()) {
        notif.dismiss()
        return false
      }
      error.value = 'Failed to add document to collection'
      console.error('Error adding document to collection:', err)
      notif.error(err instanceof IncompleteWriteError ? err.message : 'Failed to add document to collection')
      // Some links may have been written; show the collection as it is now.
      if (err instanceof IncompleteWriteError) await fetchDocumentsByCollection(collectionId)
      return false
    } finally {
      if (inSession()) loading.value = false
    }
  }

  const removeFromCollection = async (documentId: string, collectionId: string) => {
    const notif = ongoingNotification('Removing document from collection...')
    const inSession = captureSession()
    error.value = null
    loading.value = true
    try {
      await documentsRepository.removeFromCollection(documentId, collectionId)
      if (!inSession()) {
        notif.dismiss()
        return true
      }
      await fetchDocumentsByCollection(collectionId)
      notif.success('Document removed from collection')
      return true
    } catch (err) {
      if (!inSession()) {
        notif.dismiss()
        return false
      }
      error.value = 'Failed to remove document from collection'
      console.error('Error removing document from collection:', err)
      notif.error(err instanceof IncompleteWriteError ? err.message : 'Failed to remove document from collection')
      if (err instanceof IncompleteWriteError) await fetchDocumentsByCollection(collectionId)
      return false
    } finally {
      if (inSession()) loading.value = false
    }
  }

  const removeManyFromCollection = async (documentIds: string[], collectionId: string) => {
    if (documentIds.length === 0) return

    const notif = ongoingNotification('Removing selected documents from collection...')
    const inSession = captureSession()
    // Hidden while pending; afterwards only the removals the backend acknowledged as
    // complete stay applied (a partly removed document stays in the collection).
    documentIds.forEach((id) => pendingRemoveIds.value.add(id))
    error.value = null
    try {
      const results = await Promise.allSettled(
        documentIds.map((documentId) => documentsRepository.removeFromCollection(documentId, collectionId))
      )
      if (!inSession()) {
        notif.dismiss()
        return
      }
      const removed = documentIds.filter((_, i) => results[i].status === 'fulfilled')
      if (listCollectionId === collectionId) {
        documents.value = documents.value.filter((doc) => !removed.includes(doc.id))
      }
      const failures = results.flatMap((r) => (r.status === 'rejected' ? [r.reason] : []))
      if (!failures.length) {
        notif.success('Selected documents removed from collection')
        return
      }
      error.value = 'Failed to remove selected documents from collection'
      console.error('Error removing selected documents from collection:', failures)
      const first = failures[0]
      notif.error(
        `Removed ${removed.length} of ${documentIds.length} documents. ` +
        (first instanceof IncompleteWriteError ? first.message : 'The others could not be removed.')
      )
    } finally {
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
    clear,
    addToCollection,
    removeFromCollection,
    removeManyFromCollection
  }
})
