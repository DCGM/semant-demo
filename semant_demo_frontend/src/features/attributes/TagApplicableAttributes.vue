<template>
  <!-- The attributes that apply to a tag, in Create/Edit Tag (#516). Applicability belongs to the
       attribute: a Selected tags attribute is switched here for this tag only, an All tags one
       is shown on and locked, and its scope is changed in Edit Attribute. Retired attributes
       are not offered, so none is revived from here. -->
  <div data-testid="tag-applicable-attributes">
    <div class="text-subtitle1">Applicable attributes</div>
    <div class="text-caption text-grey-7 q-mb-sm">
      Values of these attributes can be assigned to annotations with this tag.
      Attributes for all tags are changed in Edit Attribute.
    </div>

    <div v-if="error" class="row items-center q-gutter-sm text-negative" data-testid="tag-attributes-load-error">
      <span>Attributes unavailable: {{ error }}</span>
      <q-btn flat dense no-caps color="primary" label="Retry" :disable="disable" @click="emit('retry')" />
    </div>
    <div v-else-if="loading && !current.length" class="text-grey-7">Loading attributes…</div>
    <div v-else-if="!current.length" class="text-grey-7" data-testid="tag-attributes-empty">
      No attributes yet. Define them in Tags &amp; attributes → Attributes.
    </div>
    <template v-else>
      <q-input
        v-if="current.length > FILTER_FROM"
        v-model="filter"
        dense
        outlined
        clearable
        label="Find attribute"
        class="q-mb-sm"
        :disable="disable"
      />
      <div class="tag-applicable-attributes__list">
        <div
          v-for="attribute in shown"
          :key="attribute.id"
          class="q-py-xs"
          data-testid="tag-applicable-attribute"
        >
          <div class="row items-center no-wrap">
            <q-toggle
              :model-value="attribute.allTags || isWanted(attribute)"
              :disable="disable || !!attribute.allTags"
              :label="attribute.name"
              class="tag-applicable-attributes__toggle"
              @update:model-value="(on: boolean) => set(attribute, on)"
            />
            <span v-if="attribute.allTags" class="tag-applicable-attributes__all q-ml-sm">All tags</span>
          </div>
          <div
            v-if="errors[attribute.id]"
            class="text-negative text-caption q-ml-xl"
            role="alert"
            data-testid="tag-applicable-attribute-error"
          >
            {{ errors[attribute.id] }}
          </div>
        </div>
        <div v-if="!shown.length" class="text-grey-7">No attribute matches.</div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

import type { Attribute } from 'src/generated/api'
import { appliesToTag } from './attributeForm'

/** From how many attributes on a filter is offered. */
const FILTER_FROM = 8

const props = defineProps<{
  /** The collection's attributes, retired ones included (they are left out here). */
  attributes: Attribute[]
  /** The tag; null while it is being created. */
  tagId: string | null
  /** Whether each Selected tags attribute should apply, by id; one not listed stays as it is. */
  wanted: Record<string, boolean>
  /** A refused or failed change, by attribute id. */
  errors: Record<string, string>
  loading: boolean
  error: string | null
  disable: boolean
}>()

const emit = defineEmits<{ 'update:wanted': [Record<string, boolean>], retry: [] }>()

const filter = ref<string | null>('')
// The ones for all tags last, as in the Tags list.
const current = computed(() => {
  const active = props.attributes.filter(a => !a.retired)
  return [...active.filter(a => !a.allTags), ...active.filter(a => a.allTags)]
})
const shown = computed(() => {
  const needle = (filter.value ?? '').trim().toLowerCase()
  return needle ? current.value.filter(a => a.name.toLowerCase().includes(needle)) : current.value
})

const isWanted = (attribute: Attribute) =>
  attribute.id in props.wanted ? !!props.wanted[attribute.id] : appliesToTag(attribute, props.tagId)

function set (attribute: Attribute, on: boolean) {
  emit('update:wanted', { ...props.wanted, [attribute.id]: on })
}
</script>

<style scoped>
.tag-applicable-attributes__list {
  max-height: 320px;
  overflow-y: auto;
}

.tag-applicable-attributes__toggle {
  min-width: 0;
  overflow-wrap: anywhere;
}

.tag-applicable-attributes__all {
  flex: none;
  padding: 0 4px;
  border-radius: 3px;
  border: 1px solid var(--q-primary);
  color: var(--q-primary);
  font-size: 10px;
  line-height: 14px;
}
</style>
