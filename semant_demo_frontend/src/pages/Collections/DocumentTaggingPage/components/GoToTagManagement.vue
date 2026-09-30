<template>
  <q-btn
    unelevated
    no-caps
    color="dark"
    icon="add"
    label="Add Tags"
    class="q-ml-0"
    @click="goToTagManagement"
  />
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const $router = useRouter()
const props = defineProps<{
  collectionId: string
  beforeRedirect?:() => void
}>()

const goToTagManagement = () => {
  props.beforeRedirect?.()
  $router.push({
    name: 'collectionTags',
    params: { collectionId: props.collectionId }
  })
}
</script>
