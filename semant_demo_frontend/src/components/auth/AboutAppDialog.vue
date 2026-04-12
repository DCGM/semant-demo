<template>
  <q-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)">
    <q-card style="min-width: 360px; max-width: 480px">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6">About semANT search demo</div>
        <q-space />
        <q-btn icon="close" flat round dense v-close-popup />
      </q-card-section>

      <q-card-section class="q-pt-sm">
        <p>
          This is a demo application for AI-enhanced semantic document search
          powered by the <strong>semANT</strong> project.
        </p>
        <p>
          It combines dense vector search with LLM-based summarisation to help
          users explore large document collections efficiently.
        </p>
        <p class="text-caption text-grey-7">
          Built with FastAPI · Weaviate · Vue 3 · Quasar
        </p>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits(['update:modelValue'])

const show = computed({ get: () => props.modelValue, set: (v: boolean) => emit('update:modelValue', v) })
</script>
