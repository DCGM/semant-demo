<template>
  <div class="col-xs-12 col-sm-6 col-lg-4 col-xl-3">
    <q-card
      class="project-card cursor-pointer flex flex-center"
      title="Create new collection"
      flat
      @click="handleClick"
    >
      <q-icon name="add_circle" size="60px" color="primary" />
    </q-card>
  </div>
</template>

<script setup lang="ts">
const emit = defineEmits<{(event: 'click'): void}>()

const handleClick = () => {
  emit('click')
}
</script>

<style lang="scss" scoped>
.project-card {
  aspect-ratio: 16 / 10.5;

  border: 3px dashed $card-border-color;
  transition: transform 0.07 ease-in-out;
  &:hover {
    border: 3px dashed $primary;
    transform: scale(1.02);
  }
}
</style>
