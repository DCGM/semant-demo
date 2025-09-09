<template>
  <q-layout view="hHh LpR fFf">
    <q-header elevated class="bg-primary text-white">
      <q-toolbar class="GNL__toolbar">
        <q-btn flat dense round @click="toggleLeftDrawer" aria-label="Menu" icon="menu" class="q-mr-sm" />

        <q-toolbar-title shrink class="row items-center no-wrap toolbar-title">
          <router-link to="/" style="text-decoration: none; color: inherit;">
            <span class="q-ml-sm">semANT search demo</span>
          </router-link>
        </q-toolbar-title>
        <q-space />
      </q-toolbar>
    </q-header>

    <q-drawer v-model="leftDrawerOpen" show-if-above bordered class="bg-white" :width="200">
      <q-scroll-area class="fit">
        <q-list padding class="text-grey-8">

          <router-link to="/search/" style="text-decoration: none; color: inherit;">
            <q-item class="drawer-item" :class="{ 'drawer-item-selected': currentRoute.startsWith('/news') }" v-ripple
              clickable>
              <q-item-section avatar>
                <q-icon name="fa-solid fa-search" />
              </q-item-section>
              <q-item-section>
                <q-item-label>Document search</q-item-label>
              </q-item-section>
            </q-item>
          </router-link>

          <router-link to="/tag_manage/" style="text-decoration: none; color: inherit;">
            <q-item class="drawer-item" :class="{ 'drawer-item-selected': currentRoute.startsWith('/news') }" v-ripple
              clickable>
              <q-item-section avatar>
                <q-icon name="fa-solid fa-tag" />
              </q-item-section>
              <q-item-section>
                <q-item-label>Manage tags</q-item-label>
              </q-item-section>
            </q-item>
          </router-link>

          <router-link to="/about/" style="text-decoration: none; color: inherit;">
            <q-item class="drawer-item" :class="{ 'drawer-item-selected': currentRoute.startsWith('/public_documents') }"
              v-ripple clickable>
              <q-item-section avatar>
                <q-icon name="fa-solid fa-info-circle" />
              </q-item-section>
              <q-item-section>
                <q-item-label>About the demo</q-item-label>
              </q-item-section>
            </q-item>
          </router-link>

          <q-separator inset class="q-my-sm" />

          <div class="q-mt-md">
            <div class="flex flex-center q-gutter-xs">
              <a class="drawer-footer-link" aria-label="Privacy">Privacy</a>
              <span> · </span>
              <a class="drawer-footer-link" aria-label="Terms">Terms</a>
            </div>
          </div>
        </q-list>
      </q-scroll-area>
    </q-drawer>

    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const inputName = ref<string|undefined>('')

const route = useRoute()

const leftDrawerOpen = ref(true)

const currentRoute = computed(() => {
  return route.path ? route.path : ''
})

function toggleLeftDrawer () {
  leftDrawerOpen.value = !leftDrawerOpen.value
}

</script>

<style scoped>
.GNL__toolbar {
  height: 64px;
}

.GNL__toolbar__toolbar-input {
  width: 55%;
}

.drawer-item {
  line-height: 24px;
  border-radius: 0 24px 24px 0;
  margin-right: 12px;
}

.drawer-item-selected {
  background: #d1e2e9;
}

.q-icon {
  color: #333638;
}

.q-item__label {
  color: #2e3133;
  letter-spacing: .01785714em;
  font-size: .875rem;
  font-weight: 500;
  line-height: 1.25rem;
}

.drawer-footer-link {
  color: inherit;
  text-decoration: none;
  font-weight: 500;
  font-size: .75rem;
}

@media screen and (max-width: 600px) {
  .toolbar-title {
    display: none;
  }
}

/*&:hover
     color: #000*/
</style>
