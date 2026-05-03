<template>
  <q-card flat class="right-panel-menu">
    <q-card-section class="right-panel-menu-section">
      <div class="row items-center justify-between q-mb-md">
        <div>
          <div class="text-subtitle1 text-weight-bold">
            {{
              isAutoSelection
                ? 'Review suggestions'
                : globalSelection?.editingId
                  ? 'Edit annotation'
                  : 'Assign tag'
            }}
          </div>

          <div
            v-if="debug && globalSelection"
            class="text-caption text-grey-7 q-mt-xs"
          >
            Chunk: {{ globalSelection.chunkId }} | Range:
            {{ globalSelection.start }}-{{ globalSelection.end }}
          </div>
          <div
            v-if="
              isAutoSelection &&
              globalSelection &&
              globalSelection.confidence !== undefined
            "
            class="text-grey-8 q-mt-xs"
          >
            Suggested with confidence:
            <strong>{{ formatConfidence(globalSelection.confidence) }}</strong>
          </div>
          <div v-else-if="debug" class="text-caption text-grey-7 q-mt-xs">
            Select text in any chunk to annotate it here.
          </div>
        </div>

        <div class="row items-center q-gutter-xs">
          <q-btn
            v-if="globalSelection?.editingId && !isAutoSelection"
            flat
            round
            dense
            icon="delete"
            color="negative"
            :loading="pageLoading"
            @click="$emit('deleteEditedTag')"
          >
            <q-tooltip>Delete annotation</q-tooltip>
          </q-btn>
          <q-btn flat round dense icon="close" @click="handleClose">
            <q-tooltip>Close tag tools</q-tooltip>
          </q-btn>
        </div>
      </div>

      <div class="tag-list">
        <q-btn
          v-for="tag in availableTags"
          :key="tag.tagUuid || tag.tagName"
          class="tag-list-item"
          flat
          no-caps
          align="left"
          :disable="!globalSelection || pageLoading || isAutoSelection"
          :style="{
            opacity:
              globalSelection?.editingId &&
              globalSelection.tagId !== tag.tagUuid
                ? 0.4
                : 1
          }"
          @click="$emit('tagClick', tag.tagUuid)"
        >
          <template #default>
            <q-icon
              :name="tag.tagPictogram"
              :style="{ color: tag.tagColor }"
              class="tag-icon"
            />
            <span class="tag-label">{{ tag.tagName }}</span>
            <q-icon
              v-if="
                globalSelection?.editingId &&
                globalSelection.tagId === tag.tagUuid
              "
              name="check"
              class="q-ml-xs"
            />
          </template>
        </q-btn>

        <p
          v-if="availableTags.length === 0"
          class="text-grey-7 q-mt-sm q-mb-sm"
        >
          No tags available for this collection.
        </p>
        <div v-if="availableTags.length === 0" class="q-mt-none">
          <go-to-tag-management
            :collectionId="props.collectionId"
            :before-redirect="() => $emit('clearSelection')"
          />
        </div>
      </div>

      <q-separator v-if="isAutoSelection" class="q-mt-lg" />

      <div v-if="isAutoSelection" class="q-mt-md">
        <div class="auto-progress-box q-mb-sm">
          <div class="text-caption text-grey-7">Auto suggestions</div>
          <div class="row items-center justify-start q-gutter-xs">
            <q-btn
              flat
              round
              dense
              icon="chevron_left"
              :disable="
                pageLoading || autoSuggestionProgress.total <= 1 || !autoSuggestionProgress.hasPending
              "
              @click="$emit('previousAutoSpan')"
            >
              <q-tooltip>Previous suggestion</q-tooltip>
            </q-btn>

            <div class="text-body2 text-weight-medium auto-progress-count">
              {{ autoSuggestionProgress.current }} /
              {{ autoSuggestionProgress.remaining }}
            </div>

            <q-btn
              flat
              round
              dense
              icon="chevron_right"
              :disable="
                pageLoading || autoSuggestionProgress.total <= 1 || !autoSuggestionProgress.hasPending
              "
              @click="$emit('nextAutoSpan')"
            >
              <q-tooltip>Next suggestion</q-tooltip>
            </q-btn>
          </div>
          <div class="text-caption text-grey-7">
            {{ autoSuggestionProgress.remaining }} remaining <br />Suggestions are ordered by confidence from highest.
          </div>
        </div>

        <div class="row q-gutter-sm">
          <q-btn
            color="positive"
            icon="thumb_up"
            label="Approve"
            :loading="pageLoading"
            @click="$emit('approveAutoSpan')"
          />
          <q-btn
            color="negative"
            icon="thumb_down"
            label="Decline"
            :loading="pageLoading"
            @click="$emit('declineAutoSpan')"
          />
          <q-btn
            outline
            color="negative"
            icon="remove_done"
            label="Decline remaining"
            :disable="pageLoading || !autoSuggestionProgress.hasPending"
            @click="$emit('declineRemainingAutoSpans')"
          />
        </div>
      </div>

      <template
        v-if="
          showProbableTagsSection && (isLoadingProbableTags || hasProbableTags)
        "
      >
        <q-separator class="q-mt-lg" />

        <div
          v-if="isLoadingProbableTags"
          class="text-grey-7 text-caption q-mt-md"
        >
          Loading most probable tags...
        </div>

        <template v-else>
          <div class="text-subtitle2 q-mt-md q-mb-sm">
            Most probable tags for selected text
          </div>
          <div class="text-caption text-grey-7 q-mb-md">
            Confidence represents the certainty about relevance of tag to the
            selected text.
          </div>

          <div class="tag-list">
            <q-btn
              v-for="tag in probableTags"
              :key="`probable-${tag.tagId}`"
              class="tag-list-item"
              :disable="!globalSelection || pageLoading"
              flat
              no-caps
              align="left"
              :style="{
                opacity:
                  globalSelection?.editingId &&
                  globalSelection.tagId !== tag.tagId
                    ? 0.4
                    : 1
              }"
              @click="$emit('tagClick', tag.tagId)"
            >
              <template #default>
                <q-icon
                  :name="tag.tagPictogram"
                  :style="{ color: tag.tagColor }"
                  class="tag-icon"
                />
                <span class="tag-label">{{ tag.tagName }}</span>

                <span class="text-caption text-grey-9 q-ml-auto">
                  Confidence: {{ formatConfidence(tag.confidence) }}
                </span>
                <q-tooltip class="text-body2">{{ tag.reason }}</q-tooltip>
              </template>
            </q-btn>
          </div>
        </template>
      </template>

      <p
        v-if="
          showProbableTagsSection && !isLoadingProbableTags && !hasProbableTags
        "
        class="text-grey-7 q-mt-lg"
      >
        There were no relevant tags suggested for the selected text.
      </p>

      <q-separator v-if="!isAutoSelection" class="q-mt-lg" />

      <div v-if="!isAutoSelection" class="q-mt-md">
        <div class="row q-gutter-sm">
          <q-btn
            unelevated
            label="Cancel"
            color="grey-8"
            :disable="!globalSelection || pageLoading"
            @click="$emit('clearSelection')"
          />
          <q-btn
            v-if="globalSelection?.editingId"
            label="Save Changes"
            color="primary"
            :loading="pageLoading"
            @click="$emit('saveEditedTag')"
          />
        </div>
      </div>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { TagSpan } from 'src/generated/api/models/TagSpan'
import { AvailableTag } from './ChunkTagAnnotator.vue'
import GoToTagManagement from './GoToTagManagement.vue'

interface GlobalSelection {
  chunkId: string
  start: number
  end: number
  editingId?: string
  tagId?: string
  spanType?: TagSpan['type']
  confidence?: number
}

interface ProbableTag {
  tagId: string
  tagName: string
  tagColor: string
  tagPictogram: string
  confidence: number
  reason: string
}

const props = defineProps<{
  debug: boolean
  globalSelection: GlobalSelection | null
  pageLoading: boolean
  isAutoSelection: boolean
  availableTags: AvailableTag[]
  probableTags: ProbableTag[]
  isLoadingProbableTags: boolean
  collectionId: string
  autoSuggestionProgress: {
    total: number
    remaining: number
    current: number
    hasPending: boolean
  }
}>()

const emit = defineEmits<{
  tagClick: [tagId: string | null]
  clearSelection: []
  saveEditedTag: []
  deleteEditedTag: []
  approveAutoSpan: []
  declineAutoSpan: []
  declineRemainingAutoSpans: []
  previousAutoSpan: []
  nextAutoSpan: []
  close: []
}>()

const formatConfidence = (confidence?: number) => {
  if (confidence === undefined) return '-'
  return `${(confidence * 100).toFixed(1)}%`
}

const showProbableTagsSection = computed(() => {
  return (
    !!props.globalSelection &&
    !props.isAutoSelection &&
    !props.globalSelection.editingId
  )
})

const hasProbableTags = computed(() => props.probableTags.length > 0)

const handleClose = () => {
  if (!props.isAutoSelection) {
    emit('clearSelection')
    return
  }

  emit('close')
}
</script>

<style scoped>
.tag-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.auto-progress-count {
  min-width: 72px;
  text-align: center;
}

.tag-list-item {
  width: 100%;
  justify-content: flex-start;
  padding: 6px 10px;
  min-height: 32px;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
  font-family: 'system-ui';
}

.tag-list-item:hover {
  background: #f5f5f5;
}

.tag-icon {
  margin-right: 10px;
  font-size: 18px;
}

.tag-label {
  font-size: 0.95rem;
  color: #1a1a1a;
}

.auto-progress-box {
  min-width: 100%;
  padding: 8px 10px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  background: #fafafa;
}
</style>
