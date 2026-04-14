<template>
  <q-btn
    size="15px"
    dense
    round
    unelevated
    color="primary"
    :icon="drawerMiniState ? 'chevron_right' : 'chevron_left'"
    @click="miniStateClick"
  />
</template>

<script setup lang="ts">

defineProps<{
  drawerMiniState: boolean;
}>()

const emit = defineEmits(['click'])

const miniStateClick = () => {
  console.log('Mini state clicked')
  emit('click')
}

</script>
