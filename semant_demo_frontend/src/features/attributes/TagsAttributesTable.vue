<template>
  <!-- The collection's tags with the attributes that apply to each, read-only (#506): those that
       name the tag, then those for all tags. Changing them from the tag side is #516. -->
  <TagsTable>
    <template #attributes="{ tag }">
      <span v-if="error" class="text-grey-7" data-testid="tag-attributes-error">Attributes unavailable</span>
      <span v-else-if="loading && !loaded" class="text-grey-7">Loading…</span>
      <template v-else>
        <WrappingBadges
          v-if="attributesOfTag(attributes, tag.id).length"
          :watch-key="attributesOfTag(attributes, tag.id)"
          :expanded-lines="4"
          :badge-height="22"
          data-testid="tag-attributes"
        >
          <span
            v-for="{ attribute, allTags } in attributesOfTag(attributes, tag.id)"
            :key="attribute.id"
            class="tag-attribute"
            data-testid="tag-attribute"
          >
            {{ attribute.name }}<span v-if="allTags" class="tag-attribute__all">All tags</span>
          </span>
        </WrappingBadges>
        <span v-else class="text-grey-7">-</span>
      </template>
    </template>
  </TagsTable>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute } from 'vue-router'

import TagsTable from 'src/features/annotations/TagsTable.vue'
import WrappingBadges from 'src/shared/ui/WrappingBadges.vue'
import { useAttributesStore } from './attributesStore'
import { attributesOfTag } from './attributeForm'

const route = useRoute()
const store = useAttributesStore()
const { attributes, loading, error } = storeToRefs(store)
// Whether a list has answered, so "-" never stands for "not loaded yet".
const loaded = ref(false)

const collectionId = computed(() => {
  const value = route.params.collectionId
  return typeof value === 'string' ? value : ''
})

async function load () {
  if (!collectionId.value) return
  loaded.value = false
  await store.load(collectionId.value)
  loaded.value = true
}

onMounted(load)
watch(collectionId, load)
</script>

<style scoped>
.tag-attribute {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 22px;
  max-width: 100%;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid #d8d8d8;
  background: #f1f1f1;
  color: rgba(0, 0, 0, 0.8);
  font-size: 12px;
  line-height: 20px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tag-attribute__all {
  padding: 0 4px;
  border-radius: 3px;
  border: 1px solid var(--q-primary);
  color: var(--q-primary);
  font-size: 10px;
  line-height: 14px;
}
</style>
