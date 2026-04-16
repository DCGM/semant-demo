<template>
  <q-card
    class="menu-card"
    :class="globalSelection ? 'bg-blue-grey-1' : 'bg-grey-2'"
  >
    <q-card-section>
      <div class="text-h6">
        {{ globalSelection?.editingId ? 'Edit Tag' : 'Global Selection' }}
      </div>
      <div v-if="globalSelection" class="text-caption text-grey-7 q-mt-xs">
        Chunk: {{ globalSelection.chunkId }} | Range:
        {{ globalSelection.start }}-{{ globalSelection.end }}
      </div>
      <div v-else class="text-caption text-grey-7 q-mt-xs">
        Select text in any chunk to annotate it here.
      </div>
    </q-card-section>

    <q-separator />

    <q-card-section>
      <div class="text-subtitle1 text-weight-bold q-mb-sm">
        {{
          isAutoSelection
            ? 'Review Suggested Tag'
            : globalSelection?.editingId
              ? 'Tag Type'
              : 'Assign Tag'
        }}
      </div>
      <div class="row q-gutter-sm">
        <q-btn
          v-for="tag in availableTags"
          :key="tag.tagUuid || tag.tagName"
          :label="tag.tagName"
          :icon="tag.tagPictogram"
          :disable="!globalSelection || pageLoading || isAutoSelection"
          :style="{
            backgroundColor: tag.tagColor,
            color: '#fff',
            opacity:
              globalSelection?.editingId &&
              globalSelection.tagId !== tag.tagUuid
                ? 0.4
                : 1
          }"
          @click="$emit('tagClick', tag.tagUuid)"
        >
          <q-icon
            v-if="
              globalSelection?.editingId &&
              globalSelection.tagId === tag.tagUuid
            "
            name="check"
            class="q-ml-xs"
          />
        </q-btn>

        <p v-if="availableTags.length === 0" class="text-grey-7 q-mt-sm">
          No tags available for this collection. Add some.
        </p>
      </div>

      <div v-if="isAutoSelection" class="row q-gutter-sm q-mt-md">
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
      </div>
    </q-card-section>

    <q-card-actions class="q-pa-md bg-grey-3 row justify-between items-center">
      <q-btn
        v-if="globalSelection?.editingId"
        flat
        icon="delete"
        label="Remove Tag"
        color="negative"
        :loading="pageLoading"
        @click="$emit('deleteEditedTag')"
      />
      <div v-else></div>

      <div class="row q-gutter-sm">
        <q-btn
          flat
          label="Cancel"
          color="grey-8"
          :disable="!globalSelection || pageLoading"
          @click="$emit('clearSelection')"
        />
        <q-btn
          v-if="globalSelection?.editingId && !isAutoSelection"
          label="Save Changes"
          color="primary"
          :loading="pageLoading"
          @click="$emit('saveEditedTag')"
        />
      </div>
    </q-card-actions>
  </q-card>
</template>

<script setup lang="ts">
import { TagSpan } from 'src/generated/api/models/TagSpan'
import { AvailableTag } from './ChunkTagAnnotator.vue'

interface GlobalSelection {
  chunkId: string
  start: number
  end: number
  editingId?: string
  tagId?: string
  spanType?: TagSpan['type']
}

defineProps<{
  globalSelection: GlobalSelection | null
  pageLoading: boolean
  isAutoSelection: boolean
  availableTags: AvailableTag[]
}>()

defineEmits<{
  tagClick: [tagId: string | null]
  clearSelection: []
  saveEditedTag: []
  deleteEditedTag: []
  approveAutoSpan: []
  declineAutoSpan: []
}>()
</script>

<style scoped>
.menu-card {
  position: sticky;
  top: 100px;
}
</style>
