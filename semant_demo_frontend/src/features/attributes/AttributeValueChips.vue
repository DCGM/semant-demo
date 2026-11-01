<template>
  <!-- The values an annotation holds of one attribute, as compact chips (#331). Unknown and
       Not applicable are set apart from ordinary values, retired ones muted, and an id the
       attribute no longer defines is shown as such (ADR 0011). Values kept on an annotation whose tag
       the attribute does not apply to (#500) are greyed and marked, not shown as valid ones. -->
  <span
    class="attribute-chips"
    :class="{ 'attribute-chips--line': line, 'attribute-chips--inapplicable': inapplicable && held.length }"
    data-testid="attribute-chips"
  >
    <span v-if="!held.length" class="attribute-chips__none">{{ emptyLabel }}</span>
    <q-icon
      v-else-if="inapplicable"
      name="do_not_disturb_on"
      size="1.1em"
      class="attribute-chips__inapplicable-icon"
      data-testid="attribute-chips-inapplicable"
      aria-hidden="true"
    />
    <span
      v-for="h in held"
      :key="h.id"
      class="attribute-chips__chip"
      :class="{
        'attribute-chips__chip--special': h.value && isSpecial(h.value),
        'attribute-chips__chip--retired': h.value?.retired,
        'attribute-chips__chip--unknown': !h.value
      }"
      :title="chipTitle(h)"
    >{{ heldName(h) }}</span>
    <span v-if="inapplicable && held.length" class="attribute-chips__sr">(does not apply to this tag)</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { QIcon } from 'quasar'
import type { Attribute } from 'src/generated/api'
import { isSpecial } from './attributeForm'
import { heldName, heldValues, type HeldValue } from './assignment'

const props = withDefaults(defineProps<{
  attribute: Attribute
  ids?: string[]
  /** Shown when the annotation holds no value. */
  emptyLabel?: string
  /** Keep to one line, cutting off what does not fit (a KWIC row stays one line). */
  line?: boolean
  /** The attribute does not apply to the annotation's tag (any more): the values are kept but
   * are not valid classifications (#500). */
  inapplicable?: boolean
}>(), {
  ids: () => [],
  emptyLabel: 'Not assigned',
  line: false,
  inapplicable: false
})

const held = computed(() => heldValues(props.attribute, props.ids))

function chipTitle (h: HeldValue): string {
  const notes = [h.value?.retired ? 'retired' : '', props.inapplicable ? 'does not apply to this tag' : ''].filter(Boolean)
  return notes.length ? `${heldName(h)} (${notes.join(', ')})` : heldName(h)
}
</script>

<style scoped>
.attribute-chips {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 2px 4px;
  min-width: 0;
  max-width: 100%;
}

.attribute-chips--line {
  flex-wrap: nowrap;
  overflow: hidden;
}

.attribute-chips__inapplicable-icon {
  flex: 0 0 auto;
  align-self: center;
  color: rgba(0, 0, 0, 0.45);
}

.attribute-chips--inapplicable .attribute-chips__chip {
  background: transparent;
  border: 1px dashed rgba(0, 0, 0, 0.35);
  color: rgba(0, 0, 0, 0.55);
}

.attribute-chips__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.attribute-chips__none {
  color: rgba(0, 0, 0, 0.45);
  font-style: italic;
}

.attribute-chips__chip {
  flex: 0 1 auto;
  max-width: 12rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 0 6px;
  border-radius: 9px;
  background: #e3ecfa;
  color: #1a3f73;
  font-size: 0.75rem;
  line-height: 1.5;
}

.attribute-chips__chip--special {
  background: #eeeeee;
  color: #424242;
  font-style: italic;
}

.attribute-chips__chip--retired {
  opacity: 0.6;
  text-decoration: line-through;
}

.attribute-chips__chip--unknown {
  background: #fdecea;
  color: #8e1b1b;
  font-style: italic;
}
</style>
