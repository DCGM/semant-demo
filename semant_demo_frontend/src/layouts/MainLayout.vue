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

        <!-- User avatar with auth menu -->
        <q-btn flat round dense>
          <q-avatar size="36px" :color="userStore.isLoggedIn ? undefined : 'grey-5'" text-color="primary">
            <img v-if="userStore.isLoggedIn" src="/boy-avatar2.png" style="border-radius:50%;width:100%;height:100%;object-fit:cover;" />
            <q-icon v-else name="person_outline" />
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

    <LoginDialog v-model="showLogin" />
    <RegisterDialog v-model="showRegister" />
    <UserInfoDialog v-model="showUserInfo" />
    <AboutAppDialog v-model="showAbout" />
  </q-layout>
</template>

<script setup lang="ts">
import MiniStateButton from 'src/components/MiniStateButton.vue'
import { ref } from 'vue'
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useQuasar } from 'quasar'
import { useUserStore } from 'src/stores/user-store'
import LoginDialog from 'src/components/auth/LoginDialog.vue'
import RegisterDialog from 'src/components/auth/RegisterDialog.vue'
import UserInfoDialog from 'src/components/auth/UserInfoDialog.vue'
import AboutAppDialog from 'src/components/auth/AboutAppDialog.vue'

const drawerMiniState = ref(false)

const route = useRoute()
const userStore = useUserStore()
const $q = useQuasar()

const leftDrawerOpen = ref(true)
const showLogin = ref(false)
const showRegister = ref(false)
const showUserInfo = ref(false)
const showAbout = ref(false)

onMounted(async () => {
  // Restore session if a token exists in localStorage
  await userStore.fetchCurrentUser()
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

const drawerLinks4 = [{ icon: 'logout', label: 'Sign out' }]

function toggleLeftDrawer () {
  leftDrawerOpen.value = !leftDrawerOpen.value
}

async function handleLogout () {
  await userStore.logout()
  $q.notify({
    type: 'info',
    message: 'You have been logged out.',
    position: 'top',
    timeout: 3000
  })
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
