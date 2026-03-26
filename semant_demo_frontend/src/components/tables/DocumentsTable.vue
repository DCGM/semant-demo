<template>
  <q-table
    title="Collection Documents"
    flat
    :columns="columns"
  >

  </q-table>
</template>

<script setup lang="ts">

const columns = [
  {
    name: 'expand',
    label: '',
    field: () => null,
    align: 'center' as const,
    style: 'width: 40px',
    required: true
  }
]

</script>
