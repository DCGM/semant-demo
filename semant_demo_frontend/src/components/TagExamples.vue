<template>
  <div class="tag-examples">
    <div
      class="examples-toggle text-caption text-grey-7"
      @click="expanded = !expanded"
    >
      <q-icon :name="expanded ? 'expand_less' : 'expand_more'" size="16px" />
      <span>{{ examples.length }} example{{ examples.length !== 1 ? 's' : '' }}</span>
    </div>

    <div v-if="expanded" class="examples-body">
      <div v-if="!examples.length && !adding" class="text-caption text-grey-5 q-py-xs">
        No examples yet.
      </div>

      <div v-for="(example, index) in examples" :key="index" class="example-chip">
        <span class="example-text">{{ example }}</span>
        <q-btn
          flat
          round
          dense
          size="xs"
          icon="close"
          class="remove-btn"
          @click="removeExample(index)"
        />
      </div>

      <div v-if="adding" class="add-example-row">
        <q-input
          v-model="newExample"
          dense
          outlined
          placeholder="New example…"
          class="add-example-input"
          @keyup.enter="confirmAdd"
          @keyup.escape="cancelAdd"
          autofocus
        >
          <template #append>
            <q-btn flat dense round size="sm" icon="check" color="positive" @click="confirmAdd" />
            <q-btn flat dense round size="sm" icon="close" color="grey-6" @click="cancelAdd" />
          </template>
        </q-input>
      </div>

      <q-btn
        v-if="!adding"
        flat
        dense
        no-caps
        size="sm"
        icon="add"
        label="Add example"
        class="add-example-btn q-mt-xs"
        @click="adding = true"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useQuasar } from 'quasar'

const $q = useQuasar()

const props = defineProps<{
  examples: string[]
  tagName: string
}>()

const emit = defineEmits<{(e: 'update', examples: string[]): void
}>()

const expanded = ref(false)
const adding = ref(false)
const newExample = ref('')

const confirmAdd = () => {
  const trimmed = newExample.value.trim()
  if (!trimmed) return
  emit('update', [...props.examples, trimmed])
  newExample.value = ''
  adding.value = false
}

const cancelAdd = () => {
  newExample.value = ''
  adding.value = false
}

const removeExample = (index: number) => {
  $q.dialog({
    title: 'Remove example',
    message: `Remove "${props.examples[index]}" from tag ${props.tagName}?`,
    cancel: true,
    ok: {
      label: 'Delete',
      color: 'negative'
    },
    persistent: false
  }).onOk(() => {
    const updated = [...props.examples]
    updated.splice(index, 1)
    emit('update', updated)
  })
}
</script>

<style scoped>
.tag-examples {
  padding-left: 28px;
  margin-top: 2px;
}

.examples-toggle {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  cursor: pointer;
  user-select: none;
  border-radius: 4px;
  padding: 1px 4px;
}

.examples-toggle:hover {
  background: rgba(15, 23, 42, 0.06);
}

.examples-body {
  margin-top: 4px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.example-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: rgba(15, 23, 42, 0.05);
  border-radius: 6px;
  padding: 2px 8px;
  font-size: 0.82rem;
  color: #475569;
  line-height: 1.4;
}

.example-chip .remove-btn {
  color: #94a3b8;
  opacity: 0;
  transition: opacity 0.15s;
}

.example-chip:hover .remove-btn {
  opacity: 1;
}

.example-text {
  flex: 1;
  word-break: break-word;
}

.add-example-row {
  margin-top: 2px;
}

.add-example-input {
  font-size: 0.82rem;
}

.add-example-btn {
  color: #64748b;
  font-size: 0.78rem;
  align-self: flex-start;
}
</style>
