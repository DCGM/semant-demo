<template>
  <div class="avatar-wrapper"
    :class="getBorderClass(props.annotationClass.approved)"
    @mouseenter="active = true" @mouseleave="active = false">
    <div v-if="active">
      <q-avatar :size="props.size"
              :style="{
                backgroundColor: leftHover ? '#858585' : props.annotationClass.colorString,
                width: 'auto', }"
              :text-color="textColorSwitcher(props.annotationClass.colorString)"
              class="avatar left"
              @mouseenter="leftHover = true"
              @mouseleave="leftHover = false"
              @click="handleLeftClick">
      {{ props.annotationClass.short }}
      </q-avatar>
      <q-avatar :size="props.size"
                :style="{
                  backgroundColor: rightHover ? '#858585' : '#C10015'}"
                text-color="white"
                icon="close"
                class="avatar right"
                square
                @mouseenter="rightHover = true"
                @mouseleave="rightHover = false"
                @click.stop="handleRightClick">
      </q-avatar>
    </div>
    <div v-else>
      <q-avatar :size="props.size"
          :style="{
            backgroundColor: props.annotationClass.colorString,
            width: 'auto', }"
          :text-color="textColorSwitcher(props.annotationClass.colorString)"
          class="roundedAvatar"
          @click="handleLeftClick">
        {{ props.annotationClass.short }}
      </q-avatar>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { defineProps, withDefaults, ref } from 'vue'
import { AnnotationClass } from 'src/models'
import { textColorSwitcher } from '../utils/textColorSwitch' // // "props.annotationClass.textColor"

const active = ref(false)
const leftHover = ref(false)
const rightHover = ref(false)

interface Props {
  annotationClass: AnnotationClass,
  size?: string
}

const props = withDefaults(defineProps<Props>(), {
  size: 'sm'
})

const emit = defineEmits<{(e: 'approve-click', annotation: AnnotationClass): void
(e: 'disapprove-click', annotation: AnnotationClass): void}>()

function getBorderClass (type: 'automatic' | 'positive' | 'negative') {
  switch (type) {
    case 'automatic':
      return 'border-automatic'
    case 'positive':
      return 'border-positive'
    case 'negative':
      return 'border-negative'
    default:
      return ''
  }
}

function handleLeftClick () {
  console.log('Left avatar clicked:', props.annotationClass)
  emit('approve-click', props.annotationClass)
}

function handleRightClick () {
  console.log('Right avatar clicked (close):', props.annotationClass)
  emit('disapprove-click', props.annotationClass)
}

</script>
<style scoped>

.roundedAvatar {
  border-radius: 3px;
}

.avatar-wrapper {
  display: inline-flex; /* make avatars sit side by side */
  border: 4px solid transparent; /* border */
  border-radius: 8px;
  transition: border 0.2s ease;
  background-color: gray;
}

.avatar {
  border-radius: 6px; /* default when alone */
  transition: border-radius 0.2s ease;
}

/* when both are visible, flatten touching corners */
.avatar.left {
  border-top-right-radius: 0;
  border-bottom-right-radius: 0;
}

.avatar.right {
  border-top-left-radius: 0;
  border-bottom-left-radius: 0;
}

/* border colors */
.border-automatic {
  border-color: gray;
  background-color: gray;
}

.border-positive {
  border-color: green;
  background-color: green;
}

.border-negative {
  border-color: red;
  background-color: red;
}

</style>
