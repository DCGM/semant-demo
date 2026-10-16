<template>
  <q-drawer
    v-model="drawerOpen"
    side="right"
    bordered
    :breakpoint="breakpoint"
    :width="width"
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
          :aria-label="panel.label"
          :aria-current="panel.id === sidebar.activePanelId ? 'true' : undefined"
          :aria-busy="panel.busy ? 'true' : undefined"
          @click="sidebar.activate(panel.id)"
        >
          <q-item-section class="avatar" avatar>
            <q-icon :name="panel.icon" />
            <q-spinner v-if="panel.busy" class="rail-busy" color="primary" size="12px" />
          </q-item-section>
          <q-tooltip class="text-subtitle2" anchor="center left" self="center right">
            {{ panel.label }}
          </q-tooltip>
        </q-item>
      </q-list>

      <q-separator v-show="!sidebar.miniState" vertical />

      <div v-show="!sidebar.miniState" class="col column no-wrap">
        <div class="row items-center no-wrap q-pl-md q-pr-sm q-pt-md q-pb-sm">
          <div class="col text-subtitle1 text-weight-medium text-grey-9" data-testid="right-sidebar-title">
            {{ sidebar.activePanel?.label }}
          </div>
          <!-- As an overlay the drawer can cover the header's toggle (phones). -->
          <q-btn v-if="overlay" flat round dense icon="close" aria-label="Close sidebar" @click="sidebar.open = false" />
        </div>
        <!-- A plain scroller (not q-scroll-area), so a panel with fill gets a definite height. -->
        <div ref="target" class="col column no-wrap scroll q-px-md q-pb-md" />
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
import MiniStateButton from 'src/app/MiniStateButton.vue'
import { useRightSidebarStore } from './rightSidebarStore'

// same as the q-drawer default, used by the left drawer
const breakpoint = 1023
const railWidth = 48

const $q = useQuasar()
const sidebar = useRightSidebarStore()
const target = ref<HTMLElement | null>(null)

// Below the breakpoint the drawer covers the page instead of pushing it.
const overlay = computed(() => $q.screen.width <= breakpoint)
// No wider than a phone screen, so the rail stays on it.
const width = computed(() => Math.min(420, $q.screen.width || 420))

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

// The drawer re-creates its content when it switches between the pushing and the overlay
// mode (e.g. on a narrow window right after load), so follow the element, not only the
// first one.
watch(target, (el) => { sidebar.targetEl = el }, { flush: 'post' })

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
    position: relative;

    .q-icon {
      color: #5f6368;
    }
  }
}

.rail-busy {
  position: absolute;
  right: -6px;
  bottom: -4px;
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
