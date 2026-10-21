<template>
  <q-btn-dropdown
    dense
    outline
    no-caps
    color="primary"
    icon="sell"
    :label="label"
    :disable="disable || !tags.length"
    :data-testid="testid"
  >
    <q-list dense class="review-tag-menu" role="menu" :aria-label="label">
      <q-item
        v-for="tag in tags"
        :key="tag.id"
        v-close-popup
        clickable
        role="menuitem"
        :disable="tag.id === currentTagId"
        @click="emit('pick', tag.id)"
      >
        <q-item-section side>
          <span class="review-tag-menu__dot" :style="{ backgroundColor: tag.color }" aria-hidden="true" />
        </q-item-section>
        <q-item-section>{{ tag.name }}</q-item-section>
      </q-item>
    </q-list>
  </q-btn-dropdown>
</template>

<script setup lang="ts">
import { QBtnDropdown, QItem, QItemSection, QList, ClosePopup as vClosePopup } from 'quasar'
import type { Tag } from 'src/generated/api'

withDefaults(defineProps<{
  tags: Tag[]
  label: string
  disable?: boolean
  /** The tag the target already has (one annotation); not offered. */
  currentTagId?: string | null
  testid?: string
}>(), {
  disable: false,
  currentTagId: null,
  testid: undefined
})

const emit = defineEmits<{ pick: [tagId: string] }>()
</script>

<style scoped>
.review-tag-menu {
  max-height: 50vh;
  overflow-y: auto;
}

.review-tag-menu__dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
</style>
