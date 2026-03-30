import { ref } from 'vue'

const useColorPicker = (color: string) => {
  const currentColor = ref<string>(color)
  const tempColor = ref<string>(color)
  const showColorPicker = ref<boolean>(false)

  const openColorPicker = () => {
    tempColor.value = currentColor.value
    showColorPicker.value = true
  }

  const confirmColor = () => {
    currentColor.value = tempColor.value
  }

  const closeColor = () => {
    showColorPicker.value = false
  }

  return {
    currentColor,
    tempColor,
    showColorPicker,

    openColorPicker,
    confirmColor,
    closeColor
  }
}

export default useColorPicker
