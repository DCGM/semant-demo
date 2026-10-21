<template>
  <q-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)">
    <q-card style="min-width: 360px; max-width: 480px">
      <q-card-section class="row items-center no-wrap q-pb-none">
        <img :src="semantLogo" alt="semANT logo" style="height: 48px; width: auto" class="q-mr-sm" />
        <div class="text-h6">About semANT demo</div>
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
import semantLogo from 'src/assets/semant-logo.png'

defineProps<{ modelValue: boolean }>()
defineEmits(['update:modelValue'])
</script>
