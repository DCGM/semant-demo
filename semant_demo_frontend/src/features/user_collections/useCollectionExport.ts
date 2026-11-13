import { ref } from 'vue'
import { Notify } from 'quasar'
import { apiErrorMessage, startDownload, useApi } from 'src/shared/api'

/**
 * Export of whole collections (#656, docs/EXPORT_FORMAT.md): every annotation of the chosen
 * collections with the text of their chunks, as one ZIP of JSON. The backend checks access
 * and returns a one-time download path; the browser's download manager then saves the ZIP.
 * A user has one running export: starting another ends the earlier download.
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
        // A failed download answer loads in a hidden frame (startDownload) and cannot be shown.
        message: `${collectionIds.length === 1 ? 'Export' : `Export of ${collectionIds.length} collections`} ` +
          'started. If no download starts within a few seconds, start the export again.'
      })
      return true
    } catch (err) {
      Notify.create({
        type: 'negative',
        position: 'top',
        message: await apiErrorMessage(err, 'The export could not be started.')
      })
      return false
    } finally {
      requesting.value = false
    }
  }

  return { exportCollections, requesting }
}
