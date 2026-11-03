<template>
  <nav class="page-strip" aria-label="Pages">
    <q-virtual-scroll
      ref="scroller"
      class="page-strip__scroller"
      virtual-scroll-horizontal
      :items="pages"
      :virtual-scroll-item-size="ITEM_WIDTH"
      :virtual-scroll-slice-size="24"
      :virtual-scroll-slice-ratio-before="0.5"
      :virtual-scroll-slice-ratio-after="0.5"
    >
      <template #default="{ item, index }">
        <button
          :key="item.pageId"
          type="button"
          class="page-strip__item"
          :class="{ 'page-strip__item--current': index === currentIndex }"
          :aria-current="index === currentIndex ? 'page' : undefined"
          :aria-label="pageName(item, index)"
          :data-page-id="item.pageId"
          data-testid="page-thumbnail"
          @click="emit('select', index)"
        >
          <img
            v-if="item.thumbnailUrl"
            class="page-strip__thumb"
            :src="assetUrl(item.thumbnailUrl)"
            alt=""
            loading="lazy"
            decoding="async"
          />
          <span v-else class="page-strip__thumb page-strip__thumb--none">
            <q-icon :name="item.imageUrl ? 'image' : 'hide_image'" size="20px" />
          </span>
          <span class="page-strip__label">{{ item.label ?? index + 1 }}</span>
        </button>
      </template>
    </q-virtual-scroll>
  </nav>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import type { QVirtualScroll } from 'quasar'
import type { DocumentPage } from 'src/generated/api'
import { assetUrl } from './pageAssets'
import { pageName } from './pageNavigation'

// The document's pages in order as a horizontal strip of thumbnails. Only the items near
// the visible part are rendered (virtual scroll), and their thumbnails load lazily, so a
// long document neither builds thousands of elements nor downloads every thumbnail.

const props = defineProps<{
  pages: DocumentPage[]
  currentIndex: number
}>()

const emit = defineEmits<{ select: [index: number] }>()

const ITEM_WIDTH = 64
const scroller = ref<QVirtualScroll | null>(null)

function reveal () {
  if (props.currentIndex >= 0) scroller.value?.scrollTo(props.currentIndex, 'center-force')
}

watch(() => props.currentIndex, () => nextTick(reveal))
onMounted(() => nextTick(reveal))
</script>

<style scoped>
.page-strip {
  border-top: 1px solid rgba(0, 0, 0, 0.12);
  background: #fafafa;
}

/* Room for a thumbnail, its label and the horizontal scroll bar. */
.page-strip__scroller {
  height: 118px;
  padding: 4px 4px 0;
  overflow-y: hidden;
}

.page-strip__item {
  width: 60px;
  margin: 0 2px;
  padding: 3px;
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  border: 2px solid transparent;
  border-radius: 4px;
  background: none;
  cursor: pointer;
  font: inherit;
  vertical-align: top;
}

.page-strip__item:hover {
  background: rgba(0, 0, 0, 0.05);
}

.page-strip__item:focus-visible {
  outline: 2px solid var(--q-primary);
  outline-offset: 1px;
}

.page-strip__item--current {
  border-color: var(--q-primary);
  background: rgba(25, 118, 210, 0.08);
}

.page-strip__thumb {
  width: 48px;
  height: 64px;
  object-fit: contain;
  background: #eee;
}

.page-strip__thumb--none {
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(0, 0, 0, 0.45);
}

.page-strip__label {
  max-width: 52px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.75rem;
  color: rgba(0, 0, 0, 0.7);
}
</style>
