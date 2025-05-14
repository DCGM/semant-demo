<template>
  <!-- Whole image should be visible - no cropping -->
  <q-img :src="`${api.defaults.baseURL}/image?image_id=${props.image}`"
         width="100%"
         :id="props.image"
         class="intersection-item"
         :class="{
              selected: props.selected,
              positive: props.positive,
              negative: props.negative,
              fail: props.fail,
            }"
         fit="contain"
         @load="handleImageLoad"
         :style="{width: newWidth}"
  >
    <!--div class="absolute-bottom text-subtitle2 text-right title-strip">
      {{ props.image }}
    </div-->
    <div class="q-img-options">
      <q-icon name="search" @click.stop="() => handleSearch(props.image)" size="24px"/>
    </div>
    <q-checkbox
      class="image-options-checkbox"
      v-model="isChecked"
      @click="emitChecked"
      dark
      size="40px"
      color="primary"
      :style="isChecked ? 'opacity: 1' : null"
    ></q-checkbox>
  </q-img>
</template>

<script setup lang="ts">
import { ref, defineProps, defineEmits, watch } from 'vue'
import { api } from 'boot/axios'

interface Props {
  tentative: boolean
  selected: boolean
  image: string
  positive: boolean
  negative: boolean
  fail: boolean
  handleSearch: (imageId: string) => void
}
const props = defineProps<Props>()

const isChecked = ref(props.selected)
// watch for the change in property selected, to update the checked state when mark good / wrong is fired
watch(() => props.selected, (newValue) => {
  isChecked.value = newValue
})

// Default values of q-img dimensions for lazy loading
const naturalWidth = ref<number>(200)
const naturalHeight = ref<number>(200)
const newWidth = ref<string>("200px")

// Set default reactive width
newWidth.value = (naturalWidth.value * naturalWidth.value / naturalHeight.value) + "px"

// Get image dimensions after its load and update the reactive const newWidth
const handleImageLoad = () => {
  const parentElement = document.getElementById(props.image)
  const imageElement = parentElement?.querySelector('.q-img__container img') as HTMLImageElement
  if (imageElement) {
    naturalWidth.value = imageElement.naturalWidth
    naturalHeight.value = imageElement.naturalHeight
    // Update reactive width based on the real image dimensions
    newWidth.value = (200 * naturalWidth.value / naturalHeight.value) + "px"
  }
}

const emit = defineEmits(['selected'])
const emitChecked = () => {
  const date = new Date()
  const timeStamp = date.toISOString()
  emit('selected', props.image, timeStamp) // Emit the selected image ID to the parent component
}
</script>

<style scoped>
.intersection-item {
  flex: 1 1 auto;
  height: 200px;
  cursor: pointer;
  position: relative;
  min-width: 100px;
  transition: ease all 0.3s;
}
.intersection-item:hover .q-img-options {
  opacity: 1;
}
.intersection-item div img {
  object-fit: cover;
  width: 100%;
  height: 100%;
  vertical-align: middle;
  border-radius: 5px;
  transition: ease all 0.3s;
}
.q-img-options {
  position: absolute;
  width: 100%;
  top: 0;
  left: 0;
  pointer-events: none;
  color: white;
  background: rgba(0,0,0, 0.8);
  background: linear-gradient(0deg, rgba(0,0,0,0) 0%, rgba(0,0,0, 0.5) 90%, rgba(0,0,0, 0.5) 100%);
  transition: ease all 0.3s;
  opacity: 0;
  padding: 8px;
  display: flex;
  justify-content: space-between;
}
.q-img-options  i {
  z-index: 70000;
  pointer-events: all;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background-color: #1976D2;
  color: #fff;
  cursor: pointer;
}
.image-options-checkbox {
  z-index: 70001;
  pointer-events: all;
  opacity: 0;
  position: absolute;
  top: 4px;
  right: 4px;
  background-color: transparent;
  padding: 0;
}
.intersection-item:hover .image-options-checkbox {
  opacity: 1;
}
.image-options-checkbox:checked {
  opacity: 1;
}
.q-img__content .q-checkbox__inner::before {
  display: none;
}

.title-strip {
  padding-top: 3px;
  padding-right: 10px;
  padding-bottom: 3px;
  padding-left: 10px;
}

.positive {
  box-shadow: -0px 0px 7px 9px #4CAF50;
  transform: scale(0.92);
}

.negative {
  box-shadow: -0px 0px 7px 9px #F44336;
  transform: scale(0.92);
}

.fail {
  box-shadow: -0px 0px 7px 9px #9C27B0;
  transform: scale(0.92);
}

.selected {
  box-shadow: -0px 0px 7px 9px #1976D2;
  transform: scale(0.90);
}

@media screen and (max-width: 1260px) {
  .image-options-checkbox {
    opacity: 1;
  }
  .q-img-options {
    opacity: 1;
  }
}

.hightlight {
  opacity: 0.7;
}
</style>
