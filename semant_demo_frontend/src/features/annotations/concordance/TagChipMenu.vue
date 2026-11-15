<template>
  <!-- The open annotation's tag in its colour; choosing another tag in its menu retags it. -->
  <q-btn
    dense
    unelevated
    no-caps
    class="tag-chip"
    :style="{ '--tag-color': tag?.color ?? '#9e9e9e' }"
    :disable="disable || !tags.length"
    :aria-label="`Tag: ${tag?.name ?? 'Unknown tag'}. Change tag`"
    data-testid="row-retag"
  >
    <span class="tag-chip__dot" aria-hidden="true" />
    <span class="tag-chip__name">{{ tag?.name ?? 'Unknown tag' }}</span>
    <q-icon name="arrow_drop_down" size="20px" class="tag-chip__arrow" />
    <q-tooltip max-width="320px" data-testid="tag-chip-tooltip">
      <div v-if="tag?.definition" class="tag-chip__definition">{{ tag.definition }}</div>
      <div class="tag-chip__hint">Click to change the tag</div>
    </q-tooltip>
    <q-menu anchor="bottom left" self="top left">
      <q-list dense class="tag-chip__menu" role="menu" aria-label="Change tag">
        <q-item
          v-for="option in tags"
          :key="option.id"
          v-close-popup
          clickable
          role="menuitem"
          :disable="option.id === tag?.id"
          @click="emit('pick', option.id)"
        >
          <q-item-section side>
            <span class="tag-chip__option-dot" :style="{ backgroundColor: option.color }" aria-hidden="true" />
          </q-item-section>
          <q-item-section>{{ option.name }}</q-item-section>
        </q-item>
      </q-list>
    </q-menu>
  </q-btn>
</template>

<script setup lang="ts">
import { QBtn, QIcon, QItem, QItemSection, QList, QMenu, QTooltip, ClosePopup as vClosePopup } from 'quasar'
import type { Tag } from 'src/generated/api'

withDefaults(defineProps<{
  /** The annotation's tag; null when it is not known (e.g. deleted). */
  tag: Tag | null
  tags: Tag[]
  disable?: boolean
}>(), { disable: false })

const emit = defineEmits<{ pick: [tagId: string] }>()
</script>

<style scoped>
.tag-chip {
  padding: 2px 4px 2px 8px;
  border-radius: 14px;
  border: 1px solid color-mix(in srgb, var(--tag-color) 55%, transparent);
  background: color-mix(in srgb, var(--tag-color) 16%, #fff);
  color: rgba(0, 0, 0, 0.87);
  font-weight: 500;
  max-width: 100%;
}

.tag-chip__dot {
  flex: none;
  width: 10px;
  height: 10px;
  margin-right: 6px;
  border-radius: 50%;
  background: var(--tag-color);
}

.tag-chip__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag-chip__arrow {
  margin-left: 2px;
  color: rgba(0, 0, 0, 0.6);
}

.tag-chip__definition {
  margin-bottom: 4px;
  font-size: 0.8rem;
  white-space: pre-wrap;
}

.tag-chip__hint {
  opacity: 0.8;
}

.tag-chip__menu {
  max-height: 50vh;
  overflow-y: auto;
}

.tag-chip__option-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
</style>
