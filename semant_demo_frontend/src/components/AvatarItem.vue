<template>
  <q-avatar :size="props.size" :style="{ backgroundColor: props.annotationClass.colorString }"
            :text-color="props.annotationClass.textColor"
            class="roundedAvatar"
            square>
    {{ props.annotationClass.short }}
  </q-avatar>
</template>

<script lang="ts" setup>
import { defineProps } from 'vue'
import { AnnotationClass } from 'src/models'

interface Props {
  annotationClass: AnnotationClass,
  size?: string
}

const props = withDefaults(defineProps<Props>(), {
  size: 'sm'
})

</script>
<style scoped>

.roundedAvatar {
  border-radius: 3px;
}

</style>
