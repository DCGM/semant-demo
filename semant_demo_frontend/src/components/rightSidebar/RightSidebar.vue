<template>
  <q-drawer
    v-model="drawerOpen"
    side="right"
    bordered
    :breakpoint="breakpoint"
    :width="420"
    :mini="sidebar.miniState"
    :mini-width="railWidth"
  >
    <!-- Not using the q-drawer mini slot, it would recreate the content and destroy the teleport target. -->
    <div class="row no-wrap fit">
      <q-list class="rail text-grey-8 col-auto" :style="{ width: `${railWidth}px` }">
        <q-item
          v-for="panel in sidebar.sortedPanels"
          :key="panel.id"
          class="rail-item"
          :class="{ 'rail-item--active': panel.id === sidebar.activePanelId }"
          clickable
          v-ripple
          @click="sidebar.activate(panel.id)"
        >
          <q-item-section class="avatar" avatar>
            <q-icon :name="panel.icon" />
          </q-item-section>
          <q-tooltip class="text-subtitle2" anchor="center left" self="center right">
            {{ panel.label }}
          </q-tooltip>
        </q-item>
      </q-list>

      <q-separator v-show="!sidebar.miniState" vertical />

      <div v-show="!sidebar.miniState" class="col column no-wrap">
        <div class="text-subtitle1 text-weight-medium text-grey-9 q-px-md q-pt-md q-pb-sm">
          {{ sidebar.activePanel?.label }}
        </div>
        <q-scroll-area class="col">
          <div ref="target" class="q-px-md q-pb-md" />
        </q-scroll-area>
      </div>
    </div>

    <div v-if="$q.screen.gt.sm" class="absolute" style="top: 15px; left: -17px">
      <MiniStateButton side="right" :drawer-mini-state="sidebar.miniState" @click="sidebar.toggleMiniState" />
    </div>
  </q-drawer>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import MiniStateButton from 'src/components/MiniStateButton.vue'
import { useRightSidebarStore } from 'src/stores/rightSidebarStore'

// same as the q-drawer default, used by the left drawer
const breakpoint = 1023
const railWidth = 48

const $q = useQuasar()
const sidebar = useRightSidebarStore()
const target = ref<HTMLElement | null>(null)

const drawerOpen = computed({
  get: () => sidebar.hasPanels && sidebar.open,
  set: (value: boolean) => { sidebar.open = value }
})

// behave like the left drawer's show-if-above whenever a page brings its panels
watch(() => sidebar.hasPanels, (hasPanels) => {
  if (hasPanels) {
    sidebar.open = $q.screen.width > breakpoint
  }
}, { immediate: true })

onMounted(() => {
  sidebar.targetEl = target.value
})

onBeforeUnmount(() => {
  sidebar.targetEl = null
})
</script>

<style lang="scss" scoped>
.rail {
  // starts below the mini state button, which overlaps the top of the rail
  padding-top: 64px;
}

.rail-item {
  // compact item, the default avatar section is wider than the whole rail
  min-height: 44px;
  padding: 0;
  justify-content: center;

  .avatar {
    min-width: 0;
    padding-right: 0;

    .q-icon {
      color: #5f6368;
    }
  }
}

.rail-item--active {
  background-color: #e8f0fe;
  position: relative;

  &::after {
    content: '';
    position: absolute;
    right: 0;
    top: 8px;
    bottom: 8px;
    width: 3px;
    background: #1a73e8;
  }

  .avatar .q-icon {
    color: #1a73e8;
  }
}
</style>
