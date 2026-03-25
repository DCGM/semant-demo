<template>
  <BaseDropdownBtn
    label="Add Document"
    icon="add"
    color="primary"
    :items="[
      { label: 'Add From Library', icon: 'library_add', action: () => emit('browseLibrary') },
      { label: 'Create New Document', icon: 'description', action: () => emit('createDocument') },
      { label: 'Upload Document', icon: 'upload_file', action: () => emit('uploadDocument') }
    ]"
  />
</template>

<script setup lang="ts">
import BaseDropdownBtn from './BaseDropdownBtn.vue'

const emit = defineEmits(
  ['browseLibrary', 'createDocument', 'uploadDocument']
)
</script>
