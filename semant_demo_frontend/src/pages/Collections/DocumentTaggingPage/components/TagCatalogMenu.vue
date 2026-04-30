<template>
  <q-card flat class="right-panel-menu">
    <q-card-section class="right-panel-menu-section">
      <div class="row items-center justify-between q-mb-md">
        <div>
          <div class="text-subtitle1 text-weight-bold">Manage tags</div>
          <div class="text-caption text-grey-7">
            Total annotations: {{ totalAnnotations }}
          </div>
        </div>

        <div class="row items-center q-gutter-xs">
          <q-btn
            flat
            dense
            size="sm"
            label="Show all"
            @click="$emit('showAll')"
          />
          <q-btn
            flat
            dense
            size="sm"
            label="Hide all"
            @click="$emit('hideAll')"
          />
          <q-btn
            flat
            round
            dense
            icon="edit"
            @click="goToTagManagement"
          >
            <q-tooltip>Edit tags</q-tooltip>
          </q-btn>
          <q-btn flat round dense icon="close" @click="$emit('close')">
            <q-tooltip>Close tags</q-tooltip>
          </q-btn>
        </div>
      </div>

      <div v-if="availableTags.length" class="tag-catalog">
        <div
          v-for="tag in availableTags"
          :key="tag.tagUuid || tag.tagName"
          class="tag-catalog-item"
          :class="{ 'is-hidden': isHidden(tag.tagUuid) }"
        >
          <div class="tag-catalog-main row items-center no-wrap">
            <q-icon
              :name="tag.tagPictogram"
              :style="{ color: tag.tagColor }"
              class="tag-catalog-icon"
            />
            <div class="tag-catalog-text">
              <div class="tag-catalog-name">{{ tag.tagName }}</div>
              <div
                v-if="tag.tagShorthand"
                class="tag-catalog-shorthand"
                :style="{ borderColor: tag.tagColor }"
              >
                {{ tag.tagShorthand }}
              </div>
            </div>
            <div class="tag-catalog-count">
              {{ getTagCount(tag.tagUuid) }} occurrences
            </div>
            <q-btn
              flat
              round
              dense
              size="sm"
              :icon="isExpanded(tag.tagUuid) ? 'expand_less' : 'info'"
              :disable="!tag.tagUuid"
              @click="toggleDetails(tag.tagUuid)"
            >
              <q-tooltip>
                {{ isExpanded(tag.tagUuid) ? 'Hide details' : 'Show details' }}
              </q-tooltip>
            </q-btn>
            <q-btn
              flat
              round
              dense
              size="sm"
              icon="filter_center_focus"
              :disable="!tag.tagUuid"
              @click="soloTag(tag.tagUuid)"
            >
              <q-tooltip>Solo tag</q-tooltip>
            </q-btn>
            <q-btn
              flat
              round
              dense
              size="sm"
              :icon="isHidden(tag.tagUuid) ? 'visibility_off' : 'visibility'"
              :disable="!tag.tagUuid"
              class="tag-catalog-visibility"
              @click="toggleVisibility(tag.tagUuid)"
            >
              <q-tooltip>
                {{ isHidden(tag.tagUuid) ? 'Show annotations' : 'Hide annotations' }}
              </q-tooltip>
            </q-btn>
          </div>

          <q-slide-transition>
            <div v-show="isExpanded(tag.tagUuid)" class="tag-catalog-details">
              <div v-if="tag.tagDefinition" class="tag-catalog-definition">
                {{ tag.tagDefinition }}
              </div>

              <div v-if="hasExamples(tag)" class="tag-catalog-examples">
                <div class="text-caption text-grey-7 q-mb-xs">Examples</div>
                <div class="tag-catalog-example-list">
                  <div
                    v-for="example in tag.tagExamples"
                    :key="example"
                    class="tag-catalog-example"
                  >
                    {{ example }}
                  </div>
                </div>
              </div>

              <div
                v-if="!tag.tagDefinition && !hasExamples(tag)"
                class="text-caption text-grey-7"
              >
                No additional tag details available.
              </div>
            </div>
          </q-slide-transition>
        </div>
      </div>

      <div v-else class="text-caption text-grey-7">
        No tags available for this collection.
      </div>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { AvailableTag } from './ChunkTagAnnotator.vue'

const props = defineProps<{
  availableTags: AvailableTag[]
  collectionId: string
  hiddenTagIds: string[]
  tagCounts: Record<string, number>
}>()

const expandedTagId = ref<string | null>(null)

const emit = defineEmits<{
  close: []
  toggleTagVisibility: [tagId: string]
  soloTag: [tagId: string]
  showAll: []
  hideAll: []
}>()

const router = useRouter()

const isHidden = (tagId: string | null) => {
  if (!tagId) return false
  return props.hiddenTagIds.includes(tagId)
}

const toggleVisibility = (tagId: string | null) => {
  if (!tagId) return
  emit('toggleTagVisibility', tagId)
}

const soloTag = (tagId: string | null) => {
  if (!tagId) return
  emit('soloTag', tagId)
}

const getTagCount = (tagId: string | null) => {
  if (!tagId) return 0
  return props.tagCounts[tagId] ?? 0
}

const isExpanded = (tagId: string | null) => {
  if (!tagId) return false
  return expandedTagId.value === tagId
}

const hasExamples = (tag: AvailableTag) => {
  return (tag.tagExamples?.length ?? 0) > 0
}

const toggleDetails = (tagId: string | null) => {
  if (!tagId) return
  expandedTagId.value = expandedTagId.value === tagId ? null : tagId
}

const totalAnnotations = computed(() => {
  return Object.values(props.tagCounts).reduce((sum, count) => sum + count, 0)
})

const goToTagManagement = () => {
  router.push({
    name: 'collectionTags',
    params: { collectionId: props.collectionId }
  })
}
</script>

<style scoped>
.tag-catalog {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tag-catalog-item {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 4px;
  border: 1px solid #e0e0e0;
}

.tag-catalog-main {
  gap: 10px;
  min-width: 0;
}

.tag-catalog-visibility {
  margin-left: 4px;
}

.tag-catalog-item.is-hidden {
  background: #f6f6f6;
  border-color: #d8d8d8;
  opacity: 0.6;
}

.tag-catalog-icon {
  font-size: 18px;
}

.tag-catalog-text {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1 1 auto;
}

.tag-catalog-name {
  font-size: 0.95rem;
  color: #1a1a1a;
}

.tag-catalog-shorthand {
  border: 1px solid #d6d6d6;
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 0.8rem;
  color: #4a4a4a;
  background: #fafafa;
}

.tag-catalog-count {
  font-size: 0.8rem;
  color: #6a6a6a;
  margin-left: auto;
  white-space: nowrap;
}

.tag-catalog-details {
  border-top: 1px solid #e8e8e8;
  padding-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tag-catalog-definition {
  font-size: 0.9rem;
  line-height: 1.45;
  color: #333;
}

.tag-catalog-example-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tag-catalog-example {
  padding: 6px 8px;
  border-radius: 4px;
  background: #fafafa;
  border: 1px solid #ececec;
  color: #4a4a4a;
  font-size: 0.88rem;
}
</style>
