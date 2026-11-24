import { useQuasar } from 'quasar'
import type { SavedSelection } from 'src/generated/api'
import { useSavedFiltersStore } from './savedFiltersStore'

/** The name prompts, confirmations and notifications of saved filter writes (#824), shared by the
 * saved filters menu and the open saved filter's header. */
export function useSavedFilterDialogs () {
  const $q = useQuasar()
  const saved = useSavedFiltersStore()

  async function run (write: () => Promise<void>, done: string) {
    try {
      await write()
      $q.notify({ type: 'positive', message: done })
    } catch (e) {
      $q.notify({ type: 'negative', message: e instanceof Error ? e.message : String(e) })
    }
  }

  function askName (title: string, value: string, ok: string, then: (name: string) => Promise<void>) {
    $q.dialog({
      title,
      prompt: { model: value, type: 'text', isValid: (v: string) => !!v.trim() && v.trim().length <= 200, counter: true, maxlength: 200 },
      ok: { label: ok, color: 'primary', unelevated: true },
      cancel: { flat: true, color: 'primary' }
    }).onOk((name: string) => { void then(name.trim()) })
  }

  return {
    run,
    saveAs () {
      const active = saved.active
      askName(active ? 'Save as a new saved filter' : 'Save current filters', active ? `${active.name} (copy)` : '', 'Save',
        name => run(() => saved.saveAs(name), `Saved “${name}”.`))
    },
    rename (item: SavedSelection) {
      askName('Rename saved filter', item.name, 'Rename', name => run(() => saved.rename(item.id, name), `Renamed to “${name}”.`))
    },
    remove (item: SavedSelection) {
      $q.dialog({
        title: 'Delete saved filter',
        message: `Delete “${item.name}” for everyone in this collection? No annotations change.`,
        ok: { label: 'Delete', color: 'negative', unelevated: true },
        cancel: { flat: true, color: 'primary' }
      }).onOk(() => { void run(() => saved.remove(item.id), `Deleted “${item.name}”.`) })
    }
  }
}
