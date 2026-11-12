import { ref } from 'vue'
import { Notify } from 'quasar'
import { apiErrorMessage, errorStatus, startDownload, useApi } from 'src/shared/api'

/**
 * Export of whole collections (#656, docs/EXPORT_FORMAT.md): every annotation of the chosen
 * collections with the text of their chunks, as one ZIP of JSON. The backend checks access
 * and returns a one-time download path; the browser's download manager then saves the ZIP.
 */
export function useCollectionExport () {
  const requesting = ref(false)

  async function exportCollections (collectionIds: string[]): Promise<boolean> {
    if (collectionIds.length === 0 || requesting.value) return false
    requesting.value = true
    try {
      const ticket = await useApi().default.requestCollectionExportApiExportsCollectionsPost({
        collectionExportRequest: { collectionIds }
      })
      startDownload(ticket.downloadPath)
      Notify.create({
        type: 'info',
        position: 'top',
        message: collectionIds.length === 1
          ? 'Export started. Your browser downloads the file.'
          : `Export of ${collectionIds.length} collections started. Your browser downloads the file.`
      })
      return true
    } catch (err) {
      const fallback = errorStatus(err) === 409
        ? 'An export of yours is still running. Wait until its download finishes.'
        : 'The export could not be started.'
      Notify.create({ type: 'negative', position: 'top', message: await apiErrorMessage(err, fallback) })
      return false
    } finally {
      requesting.value = false
    }
  }

  return { exportCollections, requesting }
}
