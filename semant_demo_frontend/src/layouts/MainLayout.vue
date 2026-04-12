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

        <!-- User avatar with auth menu -->
        <q-btn flat round dense>
          <q-avatar size="36px" :color="userStore.isLoggedIn ? 'white' : 'grey-5'" text-color="primary">
            <q-icon :name="userStore.isLoggedIn ? 'person' : 'person_outline'" />
          </q-avatar>
          <q-menu>
            <q-list style="min-width: 180px">
              <template v-if="!userStore.isLoggedIn">
                <q-item clickable v-close-popup @click="showLogin = true">
                  <q-item-section avatar><q-icon name="login" /></q-item-section>
                  <q-item-section>Log In</q-item-section>
                </q-item>
                <q-item clickable v-close-popup @click="showRegister = true">
                  <q-item-section avatar><q-icon name="person_add" /></q-item-section>
                  <q-item-section>Register</q-item-section>
                </q-item>
              </template>
              <template v-else>
                <q-item clickable v-close-popup @click="showUserInfo = true">
                  <q-item-section avatar><q-icon name="manage_accounts" /></q-item-section>
                  <q-item-section>Account</q-item-section>
                </q-item>
                <q-item clickable v-close-popup @click="handleLogout">
                  <q-item-section avatar><q-icon name="logout" /></q-item-section>
                  <q-item-section>Log Out</q-item-section>
                </q-item>
              </template>
              <q-separator />
              <q-item clickable v-close-popup @click="showAbout = true">
                <q-item-section avatar><q-icon name="info" /></q-item-section>
                <q-item-section>About</q-item-section>
              </q-item>
            </q-list>
          </q-menu>
        </q-btn>
      </q-toolbar>
    </q-header>

    <q-drawer v-model="leftDrawerOpen" show-if-above bordered class="bg-white" :width="200">
      <q-scroll-area class="fit">
        <q-list padding class="text-grey-8">

          <router-link to="/search/" style="text-decoration: none; color: inherit;">
            <q-item class="drawer-item" :class="{ 'drawer-item-selected': route.path.startsWith('/search') }" v-ripple
              clickable>
              <q-item-section avatar>
                <q-icon name="fa-solid fa-search" />
              </q-item-section>
              <q-item-section>
                <q-item-label>Document search</q-item-label>
              </q-item-section>
            </q-item>
          </router-link>

          <router-link to="/rag/" style="text-decoration: none; color: inherit;">
            <q-item class="drawer-item" :class="{ 'drawer-item-selected': route.path.startsWith('/rag') }"
              v-ripple clickable>
              <q-item-section avatar>
                <q-icon name="fa-solid fa-search" />
              </q-item-section>
              <q-item-section>
                <q-item-label>RAG</q-item-label>
              </q-item-section>
            </q-item>
          </router-link>

          <router-link to="/tag_manage/" style="text-decoration: none; color: inherit;">
            <q-item class="drawer-item" :class="{ 'drawer-item-selected': route.path.startsWith('/tag_manage') }" v-ripple
              clickable>
              <q-item-section avatar>
                <q-icon name="fa-solid fa-tag" />
              </q-item-section>
              <q-item-section>
                <q-item-label>Manage tags</q-item-label>
              </q-item-section>
            </q-item>
          </router-link>

          <router-link to="/collection_manage/" style="text-decoration: none; color: inherit;">
            <q-item class="drawer-item" :class="{ 'drawer-item-selected': route.path.startsWith('/collection_manage') }" v-ripple
              clickable>
              <q-item-section avatar>
                <q-icon name="fa-solid fa-tag" />
              </q-item-section>
              <q-item-section>
                <q-item-label>Manage collections</q-item-label>
              </q-item-section>
            </q-item>
          </router-link>

          <router-link to="/about/" style="text-decoration: none; color: inherit;">
            <q-item class="drawer-item" :class="{ 'drawer-item-selected': route.path.startsWith('/about') }"
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

    <LoginDialog v-model="showLogin" />
    <RegisterDialog v-model="showRegister" />
    <UserInfoDialog v-model="showUserInfo" />
    <AboutAppDialog v-model="showAbout" />
  </q-layout>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from 'src/stores/user-store'
import LoginDialog from 'src/components/auth/LoginDialog.vue'
import RegisterDialog from 'src/components/auth/RegisterDialog.vue'
import UserInfoDialog from 'src/components/auth/UserInfoDialog.vue'
import AboutAppDialog from 'src/components/auth/AboutAppDialog.vue'

const inputName = ref<string|undefined>('')

const route = useRoute()
const userStore = useUserStore()

const leftDrawerOpen = ref(true)
const showLogin = ref(false)
const showRegister = ref(false)
const showUserInfo = ref(false)
const showAbout = ref(false)

onMounted(async () => {
  // Restore session if a token exists in localStorage
  await userStore.fetchCurrentUser()
})

function toggleLeftDrawer () {
  leftDrawerOpen.value = !leftDrawerOpen.value
}

async function handleLogout () {
  await userStore.logout()
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
