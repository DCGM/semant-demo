<template>
  <q-page class="q-pa-md">
    <div class="row justify-center q-mb-md">
      <span class="text-h5">Text Tagging</span>
    </div>

    <div class="row q-col-gutter-lg">
      <!-- Text Container Panel -->
      <div class="col-12 col-md-8">
        <q-card>
          <q-card-section>
            <div class="text-subtitle2 text-grey-7 q-mb-sm">
              Highlight text to select, or click an existing tag to edit
            </div>

            <div
              ref="textContainer"
              class="text-container"
              @mouseup="handleMouseUp"
            >
              <span
                v-for="(seg, idx) in renderedSegments"
                :key="idx"
                :style="getSegmentStyle(seg)"
                class="text-segment"
                @click="handleSegmentClick(seg)"
                >{{ seg.text
                }}<q-tooltip
                  v-if="seg.tags.length > 0 && !currentSelection?.editingId"
                >
                  <div v-for="tag in seg.tags" :key="tag.tagId">
                    {{ getTagName(tag.tagId) }}
                  </div>
                </q-tooltip></span
              >
            </div>
          </q-card-section>
        </q-card>
      </div>

      <!-- Tagging & Adjustments Panel -->
      <div class="col-12 col-md-4">
        <!-- Active Selection / Edit Menu -->
        <q-card v-if="currentSelection" class="bg-blue-grey-1">
          <q-card-section>
            <div class="text-h6">
              {{
                currentSelection.editingId
                  ? 'Edit Tag Boundaries'
                  : 'New Selection'
              }}
            </div>

            <div class="q-mt-md">
              <div class="row items-center q-gutter-x-sm q-mb-md">
                <span style="width: 50px" class="text-weight-bold">Start:</span>
                <q-btn
                  dense
                  flat
                  round
                  icon="remove"
                  @click="adjustStart(-1)"
                  :disable="currentSelection.start <= 0 || isProcessing"
                />
                <q-badge color="primary" class="text-subtitle1 q-px-sm">{{
                  currentSelection.start
                }}</q-badge>
                <q-btn
                  dense
                  flat
                  round
                  icon="add"
                  @click="adjustStart(1)"
                  :disable="
                    currentSelection.start >= currentSelection.end - 1 ||
                    isProcessing
                  "
                />
              </div>
              <div class="row items-center q-gutter-x-sm">
                <span style="width: 50px" class="text-weight-bold">End:</span>
                <q-btn
                  dense
                  flat
                  round
                  icon="remove"
                  @click="adjustEnd(-1)"
                  :disable="
                    currentSelection.end <= currentSelection.start + 1 ||
                    isProcessing
                  "
                />
                <q-badge color="primary" class="text-subtitle1 q-px-sm">{{
                  currentSelection.end
                }}</q-badge>
                <q-btn
                  dense
                  flat
                  round
                  icon="add"
                  @click="adjustEnd(1)"
                  :disable="
                    currentSelection.end >= (chunk?.text?.length || 0) ||
                    isProcessing
                  "
                />
              </div>
            </div>
          </q-card-section>

          <q-separator />

          <q-card-section>
            <div class="text-subtitle1 text-weight-bold q-mb-sm">
              {{
                currentSelection.editingId ? 'Change Tag Type' : 'Assign Tag'
              }}
            </div>
            <div class="row q-gutter-sm">
              <q-btn
                v-for="tag in availableTags"
                :key="tag.tagUuid"
                :label="tag.tagName"
                :icon="tag.tagPictogram"
                :disable="isProcessing"
                :style="{
                  backgroundColor: tag.tagColor,
                  color: '#fff',
                  opacity:
                    currentSelection.editingId &&
                    currentSelection.tagId !== tag.tagUuid
                      ? 0.4
                      : 1
                }"
                @click="handleTagClick(tag.tagUuid)"
              >
                <q-icon
                  v-if="
                    currentSelection.editingId &&
                    currentSelection.tagId === tag.tagUuid
                  "
                  name="check"
                  class="q-ml-xs"
                />
              </q-btn>
            </div>
          </q-card-section>

          <q-card-actions
            class="q-pa-md bg-grey-3 row justify-between items-center"
          >
            <q-btn
              v-if="currentSelection.editingId"
              flat
              icon="delete"
              label="Remove Tag"
              color="negative"
              :loading="isProcessing"
              @click="deleteEditedTag"
            />
            <div v-else></div>

            <div class="row q-gutter-sm">
              <q-btn
                flat
                label="Cancel"
                color="grey-8"
                @click="clearSelection"
                :disable="isProcessing"
              />
              <q-btn
                v-if="currentSelection.editingId"
                label="Save Changes"
                color="primary"
                :loading="isProcessing"
                @click="saveEditedTag"
              />
            </div>
          </q-card-actions>
        </q-card>

        <!-- Default Empty State -->
        <q-card v-else class="bg-grey-2">
          <q-card-section class="text-center text-grey-7 q-py-xl">
            <q-icon name="edit_note" size="48px" class="q-mb-sm" />
            <div>Select text or click an existing tag.</div>
          </q-card-section>
        </q-card>
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { useApi } from 'src/composables/useApi'
import {
  ReadTagSpansApiTagSpansChunkIdGetRequest,
  UpsertTagSpansApiTagSpansPostRequest
} from 'src/generated/api'
import { onMounted, ref, computed } from 'vue'
// Assumes you have useApi exported appropriately:
// import { useApi } from 'src/api'

// --- Types ---
interface TextChunk {
  id: string
  text: string
}

interface RenderSegment {
  text: string
  tags: any[] // Based on your API's TagSpan shape
  isSelected: boolean
  start: number
  end: number
}

interface SelectionState {
  start: number
  end: number
  editingId?: string
  tagId?: string
}

const api = useApi().default

// --- State ---
const isProcessing = ref(false)
const currentSelection = ref<SelectionState | null>(null)
const textContainer = ref<HTMLElement | null>(null)

// API-driven array of spans
const tagSpans = ref<any[]>([])

// const chunk = ref<Partial<TextChunk>>({
//   id: '0000005a-85f2-42a5-8f26-d1d9102e24ea',
//   text: 'Reslaurant Wagner\nSTRADA MÄRASESTI 28\nist vollkommen renoviert und bietet den Gästen\nein erstklasiges Buffet, Gratar und Mittagstisch.\nReichhaltige Auswahl aller Getränke. Billigste\nPreise.\nUm zahlreichen Zuspruch wird gebeten.\n\nDr. Josef Sandberg\nInternist und Venerolog.\nTel. 922\nCernaufl. str. Reg. Ferdinand 31 Tel. 922\nBehandlung für\nInnere Krankheiten\nGeschlechtskrankheiten\n\nfür Gonorrhoc u. Suphilis : Pauschalhonorare\nElcktro-Endoskopische Untersuchung u. Be-\nhandlung der Harnröhre (Kauterisation)\n\nInfolge selbständiger Erzeugung\nsämtlicher\n\nSilber- und Goldwarengegenstände\nsind wir in der Lage, unsere Ware um 20%\nbilliger als überall zu verkaufen. Es überzeuge\nsich jeder durch einen einmaligen Besuch in\nunserer Werkstätte\nKreiner & Horowitz. str. I. Flondor 29 im Hofe'
// })

type ChResponse = {
  uuid: string
  properties: {
    text: string
  }
}

type Ch = {
  id: string
  text: string
}
const chunk = ref<Ch | null>(null)

const availableTags = ref([
  {
    tagName: 'Reproduktory',
    tagShorthand: 'repr',
    tagColor: '#e91e63',
    tagPictogram: 'square',
    tagDefinition: 'Reproduktory je věc, která produkuje zvuk',
    tagExamples: ['repráky'],
    collectionName: 'repraky_collection',
    tagUuid: '01f490ee-5b1b-46b4-b0e9-73476fa9c123'
  },
  {
    tagName: 'Prezident',
    tagShorthand: 'p',
    tagColor: '#4caf50',
    tagPictogram: 'circle',
    tagDefinition: 'Hlava statu',
    tagExamples: ['EU Cesko'],
    collectionName: 'MojeKolekce',
    tagUuid: '025a38bf-81cf-41c3-aa10-74e24f362bb9'
  }
])

// --- API Functions ---
const deleteTagSpan = async (spanId: string) => {
  // try {
  //   // NOTE: You didn't provide a delete API call snippet,
  //   // so update this to match your OpenAPI client signature.
  //   await api.deleteTagSpanApiTagSpansSpanIdDelete({ spanId })
  //   console.log('Tag deleted successfully')
  // } catch (error) {
  //   console.error('Error deleting tag:', error)
  // }
}

const getChunk = async () => {
  await api
    .getFirstChunkApiGetFirstChunkGet()
    .then((response: ChResponse) => {
      chunk.value = {
        id: response.uuid,
        text: response.properties.text
      }
      console.log('Fetched chunk:', response)
    })
    .catch((error) => {
      console.error('Error fetching chunk:', error)
    })
}

const getTagSpans = async (
  chunkId: ReadTagSpansApiTagSpansChunkIdGetRequest['chunkId']
) => {
  await api
    .readTagSpansApiTagSpansChunkIdGet({ chunkId, mode: 'separate' })
    .then((response) => {
      tagSpans.value = response
      console.log('Fetched tag spans:', response)
    })
    .catch((error) => {
      console.error('Error fetching tag spans:', error)
    })
}
const createTagSpan = async (
  data: UpsertTagSpansApiTagSpansPostRequest['tagSpanWriteRequest']
) => {
  await api
    .upsertTagSpansApiTagSpansPost({
      tagSpanWriteRequest: {
        chunkId: data.chunkId,
        spans: data.spans,
        mode: 'separate',
        tagId: data.spans[0].tagId
      }
    })
    .then((response) => {
      console.log('Tag span(s) created successfully:', response)
    })
    .catch((error) => {
      console.error('Error creating tag span(s):', error)
    })
}
const updateTagSpan = async (
  chunkId: string,
  spanId: string,
  tagId: string,
  start: number,
  end: number
) => {
  await api
    .updateTagSpanApiTagSpansUpdatePatch({
      tagSpanUpdateRequest: {
        mode: 'separate',
        chunkId,
        spanId,
        tagId,
        start,
        end
      }
    })
    .then((response) => {
      console.log('Tag updated successfully:', response)
    })
    .catch((error) => {
      console.error('Error updating tag:', error)
    })
}

// --- Segment Builder Logic ---
const renderedSegments = computed(() => {
  if (!chunk.value?.text) return []
  const text = chunk.value.text
  const segments: RenderSegment[] = []

  let currentTagsStr = ''
  let currentIsSelected = false
  let currentSeg: RenderSegment | null = null

  for (let i = 0; i < text.length; i++) {
    const char = text[i]

    const activeTags = tagSpans.value.filter(
      (t) =>
        i >= t.start && i < t.end && t.id !== currentSelection.value?.editingId
    )

    activeTags.sort((a, b) => a.tagId.localeCompare(b.tagId))
    const tagsStr = activeTags.map((t) => t.tagId).join(',')

    const isSelected =
      currentSelection.value !== null &&
      i >= currentSelection.value.start &&
      i < currentSelection.value.end

    if (
      !currentSeg ||
      tagsStr !== currentTagsStr ||
      isSelected !== currentIsSelected
    ) {
      if (currentSeg) {
        currentSeg.end = i
        segments.push(currentSeg)
      }
      currentSeg = {
        text: char,
        tags: activeTags,
        isSelected,
        start: i,
        end: i + 1
      }
      currentTagsStr = tagsStr
      currentIsSelected = isSelected
    } else {
      currentSeg.text += char
    }
  }
  if (currentSeg) {
    currentSeg.end = text.length
    segments.push(currentSeg)
  }
  return segments
})

// --- Actions & Handlers ---
const handleMouseUp = () => {
  if (isProcessing.value) return // Block changes while loading

  const sel = window.getSelection()
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return

  const range = sel.getRangeAt(0)
  const container = textContainer.value
  if (
    !container ||
    (!container.contains(range.startContainer) &&
      !container.contains(range.endContainer))
  )
    return

  const preSelectionRange = range.cloneRange()
  preSelectionRange.selectNodeContents(container)
  preSelectionRange.setEnd(range.startContainer, range.startOffset)
  let start = preSelectionRange.toString().length

  const postSelectionRange = range.cloneRange()
  postSelectionRange.selectNodeContents(container)
  postSelectionRange.setEnd(range.endContainer, range.endOffset)
  let end = postSelectionRange.toString().length

  if (start > end) [start, end] = [end, start]

  currentSelection.value = { start, end }
  sel.removeAllRanges()
}

const handleSegmentClick = (seg: RenderSegment) => {
  if (currentSelection.value !== null || isProcessing.value) return

  if (seg.tags.length > 0) {
    const tagToEdit = seg.tags[0]
    currentSelection.value = {
      start: tagToEdit.start,
      end: tagToEdit.end,
      editingId: tagToEdit.id,
      tagId: tagToEdit.tagId
    }
  }
}

// --- CRUD Actions ---
const handleTagClick = async (tagId: string) => {
  if (!currentSelection.value) return

  if (!chunk.value?.id) return

  if (currentSelection.value.editingId) {
    currentSelection.value.tagId = tagId
  } else {
    // API Call: Create Mode
    isProcessing.value = true
    await createTagSpan({
      chunkId: chunk.value.id!,
      tagId,
      spans: [
        {
          id: '',
          tagId,
          start: currentSelection.value.start,
          end: currentSelection.value.end,
          chunkId: chunk.value.id!
        }
      ]
    })

    await getTagSpans(chunk.value.id!)
    clearSelection()
    isProcessing.value = false
  }
}

const saveEditedTag = async () => {
  if (!currentSelection.value || !currentSelection.value.editingId) return
  if (!chunk.value?.id) return

  isProcessing.value = true
  await updateTagSpan(
    chunk.value.id!,
    currentSelection.value.editingId,
    currentSelection.value.tagId!,
    currentSelection.value.start,
    currentSelection.value.end
  )

  await getTagSpans(chunk.value.id!)
  clearSelection()
  isProcessing.value = false
}

const deleteEditedTag = async () => {
  if (!currentSelection.value || !currentSelection.value.editingId) return
  if (!chunk.value?.id) return

  isProcessing.value = true
  await deleteTagSpan(currentSelection.value.editingId)
  await getTagSpans(chunk.value.id!)
  clearSelection()
  isProcessing.value = false
}

// --- Boundary Adjustment Actions ---
const adjustStart = (delta: number) => {
  if (!currentSelection.value) return
  const newStart = currentSelection.value.start + delta
  if (newStart >= 0 && newStart < currentSelection.value.end) {
    currentSelection.value.start = newStart
  }
}

const adjustEnd = (delta: number) => {
  if (!chunk.value?.text) return
  if (!currentSelection.value) return
  const newEnd = currentSelection.value.end + delta
  const maxLen = chunk.value.text?.length || 0
  if (newEnd > currentSelection.value.start && newEnd <= maxLen) {
    currentSelection.value.end = newEnd
  }
}

const clearSelection = () => {
  currentSelection.value = null
}

// --- Display Helpers ---
const getTagName = (tagId: string) => {
  const tag = availableTags.value.find((t) => t.tagUuid === tagId)
  return tag ? tag.tagName : 'Unknown Tag'
}

const getSegmentStyle = (seg: RenderSegment) => {
  if (seg.isSelected) {
    if (currentSelection.value?.tagId) {
      const draftTag = availableTags.value.find(
        (t) => t.tagUuid === currentSelection.value!.tagId
      )
      if (draftTag) {
        return {
          backgroundColor: draftTag.tagColor + '60',
          borderBottom: `2px solid ${draftTag.tagColor}`,
          color: '#000'
        }
      }
    }
    return {
      backgroundColor: '#ffe082',
      borderBottom: '2px solid #ffca28',
      color: '#000'
    }
  }

  if (seg.tags.length > 0) {
    const tag = availableTags.value.find((t) => t.tagUuid === seg.tags[0].tagId)
    const color = tag ? tag.tagColor : '#cccccc'
    return {
      backgroundColor: color + '40',
      borderBottom: `2px solid ${color}`,
      cursor: 'pointer'
    }
  }
  return {}
}

// Initial Data Load
onMounted(async () => {
  console.log('TaggingPage mounted')

  await getChunk()

  console.log('Chunk:', chunk.value)

  if (chunk.value?.id) {
    await getTagSpans(chunk.value.id)
  }

  // if (chunk.value.id) {
  //   getTagSpans(chunk.value.id)
  // }
})
</script>

<style scoped>
.text-container {
  white-space: pre-wrap;
  font-size: 16px;
  line-height: 1.8;
  padding: 16px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  cursor: text;
  background-color: #fafafa;
}

.text-segment {
  transition:
    background-color 0.15s,
    border-bottom 0.15s;
  border-bottom: 2px solid transparent;
  border-radius: 2px;
}
</style>
