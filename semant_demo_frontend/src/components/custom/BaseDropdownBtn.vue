<template>
  <q-btn-dropdown
    class="q-ma-sm q-px-md"
    no-caps
    unelevated
    :color="props.color"
    :label="props.label"
    :icon="props.icon"
    menu-anchor="bottom middle"
    menu-self="top middle"
  >
    <menu>
      <q-list>
        <q-item
          v-for="item in props.items"
          :key="item.label"
          clickable
          v-ripple
          v-close-popup
          @click="item.action"
        >
          <q-item-section avatar>
            <q-icon :name="item.icon" />
          </q-item-section>
          <q-item-section no-wrap>{{ item.label }}</q-item-section>
        </q-item>
      </q-list>
    </menu>
  </q-btn-dropdown>
</template>

<script setup lang="ts">

interface DropDownItemn {
  label: string
  icon?: string
  action: () => void
}

interface Props {
  label: string
  items: DropDownItemn[]
  icon?: string
  color?: string
}

const props = withDefaults(defineProps<Props>(), {
  label: 'Button'
})
</script>
