<template>
  <q-dialog ref="dialogRef" @hide="onDialogHide" :persistent="uploading">
    <q-card class="text-upload-dialog">
      <q-card-section class="row items-start no-wrap q-gutter-sm">
        <div class="col">
          <div class="text-h6">Upload text documents</div>
          <div class="text-caption text-grey-7">
            Each UTF-8 <code>.txt</code> file becomes a private document of this collection, readable only
            through it. Its title is the file name unless a metadata CSV gives one.
          </div>
        </div>
        <q-btn flat round dense icon="close" aria-label="Close dialog" :disable="uploading" @click="close" />
      </q-card-section>

      <q-separator />

      <q-card-section class="q-gutter-md">
        <q-file
          v-model="files"
          multiple
          append
          use-chips
          outlined
          counter
          accept=".txt,text/plain"
          label="Text files (.txt)"
          :max-files="MAX_FILES"
          :disable="uploading"
          data-testid="upload-files"
          @rejected="onRejected"
        >
          <template #prepend><q-icon name="description" /></template>
        </q-file>
        <div>
          <q-file
            v-model="metadata"
            clearable
            outlined
            dense
            accept=".csv,text/csv"
            label="Metadata CSV (optional)"
            :disable="uploading"
            data-testid="upload-metadata"
          >
            <template #prepend><q-icon name="table_view" /></template>
          </q-file>
          <div class="text-caption text-grey-7 q-mt-xs">
            Columns: <code>filename</code> (required, as uploaded), <code>title</code>, <code>author</code>,
            <code>yearIssued</code>, <code>language</code>, <code>description</code>.
            <a :href="templateHref" download="semant-text-upload-template.csv" data-testid="upload-template">Download the CSV template</a>
          </div>
        </div>

        <q-banner v-if="localProblems.size" dense class="bg-red-1 text-negative" data-testid="upload-local-problems">
          <div v-for="[name, problem] in localProblems" :key="name">
            <strong v-if="name">{{ name }}:</strong> {{ problem }}
          </div>
        </q-banner>
        <q-banner v-if="requestError" dense class="bg-red-1 text-negative" data-testid="upload-error">
          {{ requestError }}
        </q-banner>
      </q-card-section>

      <template v-if="response">
        <q-separator />
        <q-card-section data-testid="upload-results">
          <div class="text-subtitle2" :class="allCompleted(response) ? 'text-positive' : 'text-negative'">
            {{ summary(response) }}
          </div>
          <div v-if="files.length && !allCompleted(response)" class="text-caption text-grey-8" data-testid="upload-next">
            The files not added stay selected: correct or remove them, then upload again.
            <span v-if="metadataCleared">Choose a metadata CSV with rows for these files only.</span>
          </div>
          <ul v-if="response.errors?.length" class="q-my-sm text-negative">
            <li v-for="error in response.errors" :key="error">{{ error }}</li>
          </ul>
          <q-list dense separator>
            <q-item v-for="file in response.files" :key="file.filename" data-testid="upload-result">
              <q-item-section avatar>
                <q-icon :name="STATUS[file.status].icon" :color="STATUS[file.status].color" />
              </q-item-section>
              <q-item-section>
                <q-item-label class="ellipsis">
                  <router-link
                    v-if="file.status === 'completed' && file.documentId"
                    :to="{ name: 'documentDetailV1', params: { collectionId, documentId: file.documentId } }"
                    @click="close"
                  >{{ file.title || file.filename }}</router-link>
                  <span v-else>{{ file.filename }}</span>
                </q-item-label>
                <q-item-label caption>
                  <span :class="`text-${STATUS[file.status].color}`">{{ STATUS[file.status].label }}</span>
                  <span v-if="file.status === 'completed'"> · {{ file.filename }} · {{ plural(file.chunks ?? 0, 'passage') }}</span>
                </q-item-label>
                <q-item-label v-if="file.error" caption class="text-negative wrap">{{ file.error }}</q-item-label>
              </q-item-section>
            </q-item>
          </q-list>
        </q-card-section>
      </template>

      <q-separator />

      <q-card-actions align="right">
        <q-btn flat :label="response ? 'Close' : 'Cancel'" :disable="uploading" @click="close" />
        <q-btn
          unelevated
          color="primary"
          icon="upload"
          label="Upload"
          :loading="uploading"
          :disable="!files.length || localProblems.size > 0"
          data-testid="upload-submit"
          @click="upload"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useDialogPluginComponent } from 'quasar'
import type { TextUploadResponse } from 'src/generated/api'
import { apiErrorMessage } from 'src/shared/api'
import { plural } from 'src/shared/plural'
import { useDocumentsRepository } from '../useDocumentsRepository'
import { CSV_TEMPLATE, MAX_FILES, STATUS, allCompleted, checkFiles, filesNotSaved, summary } from './textUpload'

const props = defineProps<{ collectionId: string }>()
defineEmits([...useDialogPluginComponent.emits])
const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()
const repository = useDocumentsRepository()

const files = ref<File[]>([])
const metadata = ref<File | null>(null)
const uploading = ref(false)
const response = ref<TextUploadResponse | null>(null)
const metadataCleared = ref(false)
const requestError = ref<string | null>(null)
const rejected = ref<string | null>(null)
// Documents were added in this dialog: the collection's list is reloaded when it closes.
const added = ref(false)

const localProblems = computed(() => {
  const problems = checkFiles(files.value)
  if (rejected.value && !problems.has('')) problems.set('', rejected.value)
  return problems
})

const templateHref = URL.createObjectURL(new Blob([CSV_TEMPLATE], { type: 'text/csv' }))
onBeforeUnmount(() => URL.revokeObjectURL(templateHref))

function onRejected () {
  rejected.value = `Only .txt files can be added, at most ${MAX_FILES}.`
}

async function upload () {
  if (uploading.value || !files.value.length) return
  uploading.value = true
  requestError.value = null
  rejected.value = null
  metadataCleared.value = false
  try {
    const result = await repository.uploadTextDocuments(props.collectionId, files.value, metadata.value)
    response.value = result
    const remaining = filesNotSaved(files.value, result)
    // The CSV names the saved files too, which the server would refuse as not uploaded.
    metadataCleared.value = !!metadata.value && remaining.length > 0 && remaining.length < files.value.length
    if (metadataCleared.value) metadata.value = null
    files.value = remaining
    if (result.files.some(f => f.status === 'completed' || f.status === 'uncertain')) added.value = true
  } catch (err) {
    response.value = null
    requestError.value = await apiErrorMessage(err, 'The upload failed. Nothing was saved; try again.')
  } finally {
    uploading.value = false
  }
}

function close () {
  if (uploading.value) return
  if (added.value) onDialogOK()
  else onDialogCancel()
}
</script>

<style scoped>
.text-upload-dialog {
  width: 720px;
  max-width: 95vw;
}

.wrap {
  white-space: normal;
  overflow-wrap: anywhere;
}
</style>
