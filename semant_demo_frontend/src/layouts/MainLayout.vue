<template>
  <q-layout view="hHh Lpr fff">
    <q-header elevated class="bg-white text-grey-8">
      <q-toolbar class="GNL__toolbar">
        <q-btn class="q-mx-md" dense flat round @click="toggleLeftDrawer" icon="menu" />

        <q-toolbar-title shrink class="row items-center no-wrap toolbar-title">
          <router-link to="/" style="text-decoration: none; color: inherit;">
            <span class="q-ml-sm">semANT search demo</span>
          </router-link>
        </q-toolbar-title>
        <q-space />
      </q-toolbar>
    </q-header>

    <q-drawer
    v-model="leftDrawerOpen"
    show-if-above
    bordered
    :width="280"
    :mini="drawerMiniState"
    :mini-width="75"
    >
      <q-scroll-area class="fit">
        <q-list padding class="text-grey-8">
          <q-item
            class="drawer-item"
            v-for="link in drawerLinks1"
            :key="link.label"
            :to="link.to"
            clickable
            v-ripple
            active-class="my-active-item"
            :exact="false"
          >
            <q-item-section class="avatar" avatar>
              <q-icon :name="link.icon" />
            </q-item-section>
            <q-item-section>
              <q-item-label class="item-label">{{ link.label }}</q-item-label>
            </q-item-section>
            <q-tooltip
              class="text-subtitle2"
              anchor="center right"
              self="center left"
              v-if="drawerMiniState"
            >
              {{ link.label }}
            </q-tooltip>
          </q-item>

          <q-separator inset class="q-my-sm" />

          <q-item
            class="drawer-item"
            v-for="link in drawerLinks2"
            :key="link.label"
            :to="link.to"
            clickable
            v-ripple
          >
            <q-item-section class="avatar" avatar>
              <q-icon :name="link.icon" />
            </q-item-section>
            <q-item-section>
              <q-item-label class="item-label">{{ link.label }}</q-item-label>
            </q-item-section>
            <q-tooltip
              class="text-subtitle2"
              anchor="center right"
              self="center left"
              v-if="drawerMiniState"
            >
              {{ link.label }}
            </q-tooltip>
          </q-item>

          <q-separator inset class="q-my-sm" />

          <div v-if="!drawerMiniState">
            <q-item
              class="drawer-item"
              v-for="link in drawerLinks3"
              :key="link.label"
              :to="link.to"
              clickable
              v-ripple
            >
              <q-item-section>
                <q-item-label class="item-label">
                  {{ link.label }} <q-icon v-if="link.icon" :name="link.icon" />
                </q-item-label>
              </q-item-section>
            </q-item>

            <q-separator inset class="q-my-sm" />
          </div>

          <q-item class="drawer-item" v-for="link in drawerLinks4" :key="link.label" clickable v-ripple>
            <q-item-section class="avatar" avatar>
              <q-icon :name="link.icon" />
            </q-item-section>
            <q-item-section>
              <q-item-label class="item-label">{{ link.label }}</q-item-label>
            </q-item-section>
            <q-tooltip
              class="text-subtitle2"
              anchor="center right"
              self="center left"
              v-if="drawerMiniState"
            >
              {{ link.label }}
            </q-tooltip>
          </q-item>
        </q-list>
      </q-scroll-area>
      <div v-if="$q.screen.gt.sm" class="absolute" style="top: 15px; right: -17px">
        <MiniStateButton :drawer-mini-state="drawerMiniState" @click="miniStateClick" />
      </div>
    </q-drawer>
    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import MiniStateButton from 'src/components/MiniStateButton.vue'
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'

const drawerMiniState = ref(false)

const route = useRoute()

const leftDrawerOpen = ref(true)

const currentRoute = computed(() => {
  return route.path ? route.path : ''
})

const drawerLinks1 = [
  { label: 'Document search', icon: 'search', to: { name: 'search' } },
  { label: 'Chat Assistant', icon: 'chat', to: { name: 'rag' } },
  { label: 'Collections', icon: 'folder', to: { name: 'collections' } },
  { label: 'About', icon: 'info', to: { name: 'about' } }
]

const drawerLinks2 = [
  { label: 'Settings', icon: 'settings', to: { name: 'settings' } }
]

const drawerLinks3 = [
  { label: 'Send feedback', icon: '', to: { name: 'feedback' } }
]

const drawerLinks4 = [{ icon: 'logout', label: 'Sign out', to: { name: 'sign-out' } }]

function toggleLeftDrawer () {
  leftDrawerOpen.value = !leftDrawerOpen.value
}

const miniStateClick = () => {
  console.log('Mini state clicked')
  drawerMiniState.value = !drawerMiniState.value
}

</script>

<style lang="scss" scoped>
.GNL__toolbar {
  height: 64px;
}

.GNL__toolbar__toolbar-input {
  width: 55%;
}

.drawer-item {
  border-radius: 0 24px 24px 0;

  .avatar {
    .q-icon {
      color: #5f6368;
    }
  }

  .item-label {
    color: #3c4043;
    letter-spacing: 0.01785714em;
    font-weight: 500;
  }
}

.my-active-item {
  background-color: #e8f0fe;
  border-radius: 0 24px 24px 0;
  position: relative; /* důležité pro absolutní pozicování proužku */

  /* Barevný proužek vlevo */
  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 8px;
    bottom: 8px;
    width: 6px; /* šířka proužku */
    background: #1a73e8; /* barva proužku */
  }

  .avatar {
    .q-icon {
      color: #1a73e8;
    }
  }

  .item-label {
    color: #1a73e8;
    font-weight: 600;
  }
}

@media screen and (max-width: 600px) {
  .toolbar-title {
    display: none;
  }
}

/*&:hover
     color: #000*/
</style>
