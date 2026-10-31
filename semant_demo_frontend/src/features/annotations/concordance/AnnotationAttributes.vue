<template>
  <!-- The open annotation's attribute values in the sidebar (#331): every attribute that applies
       to its tag, each with a menu to change its values (saved at once), and values it still holds
       of attributes that no longer apply or were retired. -->
  <section class="annotation-attributes" aria-label="Attributes" data-testid="annotation-attributes">
    <div class="annotation-attributes__title text-caption">Attributes</div>
    <div v-if="loading && !attributes.length" class="text-caption text-grey-7">Loading attributes…</div>
    <div v-else-if="error" class="text-caption text-negative" role="alert">{{ error }}</div>
    <template v-else>
      <div v-if="!applicable.length && !others.length" class="text-caption text-grey-7" data-testid="annotation-attributes-empty">
        No attributes apply to this tag.
        <router-link v-if="definitionsRoute" :to="definitionsRoute">Define attributes</router-link>
      </div>
      <div v-else-if="reason" class="text-caption text-grey-7" data-testid="annotation-attributes-note">{{ reason }}</div>
      <div
        v-for="attribute in applicable"
        :key="attribute.id"
        class="annotation-attributes__row"
        :data-testid="`annotation-attribute-${attribute.id}`"
      >
        <span class="annotation-attributes__name" :title="attribute.description || attribute.name">{{ attribute.name }}</span>
        <AttributeValueChips :attribute="attribute" :ids="held(attribute)" />
        <q-btn
          v-if="!reason"
          flat
          dense
          no-caps
          size="sm"
          color="primary"
          icon="edit"
          :loading="busy"
          :aria-label="`Change ${attribute.name}`"
          data-testid="annotation-attribute-edit"
        >
          <q-menu anchor="bottom right" self="top right">
            <AttributeValuePicker
              :attribute="attribute"
              :current="held(attribute)"
              :busy="busy"
              @change="change => emit('assign', attribute, change)"
            />
          </q-menu>
        </q-btn>
      </div>
      <div
        v-for="attribute in others"
        :key="attribute.id"
        class="annotation-attributes__row annotation-attributes__row--other"
        :data-testid="`annotation-attribute-${attribute.id}`"
      >
        <span class="annotation-attributes__name">{{ attribute.name }}</span>
        <AttributeValueChips :attribute="attribute" :ids="held(attribute)" />
        <span class="text-caption text-grey-7">{{ attribute.retired ? 'retired' : 'does not apply to this tag' }}</span>
        <q-btn
          v-if="row.type === SpanType.pos"
          flat
          dense
          no-caps
          size="sm"
          color="primary"
          label="Remove"
          :loading="busy"
          :aria-label="`Remove the values of ${attribute.name}`"
          @click="emit('assign', attribute, clearChange(held(attribute)))"
        />
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { QBtn, QMenu } from 'quasar'
import { SpanType, type AnnotationListRow, type Attribute } from 'src/generated/api'
import AttributeValueChips from 'src/features/attributes/AttributeValueChips.vue'
import AttributeValuePicker from 'src/features/attributes/AttributeValuePicker.vue'
import { attributesOfTag } from 'src/features/attributes/attributeForm'
import { cannotAssign, clearChange, type AssignChange } from 'src/features/attributes/assignment'

const props = defineProps<{
  row: AnnotationListRow
  attributes: Attribute[]
  loading?: boolean
  error?: string | null
  /** An assignment of this annotation is under way. */
  busy?: boolean
  /** The collection's attribute definitions page, for the empty state. */
  definitionsRoute?: object | null
}>()

const emit = defineEmits<{ assign: [attribute: Attribute, change: AssignChange] }>()

const held = (attribute: Attribute) => props.row.attributes?.[attribute.id] ?? []

const applicable = computed(() =>
  props.row.tagId ? attributesOfTag(props.attributes, props.row.tagId).map(a => a.attribute) : [])

// Values held of attributes retired or no longer applying to the tag (#500): shown, removable.
const others = computed(() => {
  const shown = new Set(applicable.value.map(a => a.id))
  return props.attributes.filter(a => !shown.has(a.id) && held(a).length)
})

// Retirement does not apply to the applicable ones (not retired), so this is the row's own reason.
const reason = computed(() => {
  const first = applicable.value[0]
  return first ? cannotAssign(first, props.row) : null
})
</script>

<style scoped>
.annotation-attributes {
  margin: 6px 0;
  padding-top: 4px;
  border-top: 1px solid rgba(0, 0, 0, 0.08);
}

.annotation-attributes__title {
  font-weight: 600;
  color: rgba(0, 0, 0, 0.7);
  margin-bottom: 2px;
}

.annotation-attributes__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px 8px;
  min-height: 28px;
  font-size: 0.85rem;
}

.annotation-attributes__name {
  min-width: 6rem;
  max-width: 12rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgba(0, 0, 0, 0.75);
}

.annotation-attributes__row--other {
  opacity: 0.85;
}
</style>
