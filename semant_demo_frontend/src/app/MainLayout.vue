<template>
  <q-layout view="hHh LpR fff">
    <q-header elevated class="bg-white text-grey-8">
      <q-toolbar class="GNL__toolbar">
        <q-btn
          class="q-mx-md"
          dense
          flat
          round
          icon="menu"
          :aria-label="leftDrawerOpen ? 'Hide navigation' : 'Show navigation'"
          :aria-expanded="leftDrawerOpen"
          @click="toggleLeftDrawer"
        />

        <q-toolbar-title shrink class="row items-center no-wrap">
          <router-link to="/" class="row items-center no-wrap" style="text-decoration: none; color: inherit;">
            <img :src="semantLogo" alt="semANT logo" class="toolbar-logo" />
            <span class="q-ml-sm toolbar-title">semANT demo</span>
          </router-link>
        </q-toolbar-title>
        <q-space />

        <QuotaIndicator @login="showLogin = true" @register="showRegister = true" />

        <!-- User avatar with auth menu -->
        <q-btn flat round dense aria-label="User menu">
          <q-avatar size="36px" :color="userStore.isLoggedIn ? undefined : 'grey-5'" text-color="primary">
            <img v-if="userStore.isLoggedIn" src="/boy-avatar2.png" style="border-radius:50%;width:100%;height:100%;object-fit:cover;" />
            <q-icon v-else-if="userStore.restoreFailed" name="cloud_off" />
            <q-icon v-else name="person_outline" />
          </q-avatar>
          <q-menu v-model="userMenuOpen">
            <q-list style="min-width: 180px">
              <template v-if="userStore.awaitingVerification">
                <q-item clickable v-close-popup @click="handleLogout">
                  <q-item-section avatar><q-icon name="logout" /></q-item-section>
                  <q-item-section>Log Out</q-item-section>
                </q-item>
              </template>
              <template v-else-if="!userStore.isLoggedIn">
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

        <q-btn
          v-if="rightSidebar.hasPanels"
          class="q-mx-md"
          dense
          flat
          round
          aria-label="Toggle sidebar"
          @click="rightSidebar.toggleOpen"
          icon="view_sidebar"
        />
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

          <template v-if="drawerLinks2.length">
            <q-item
              class="drawer-item"
              v-for="link in drawerLinks2"
              :key="link.label"
              clickable
              v-ripple
              @click="link.action"
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
          </template>

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

          <q-item
            class="drawer-item"
            v-for="link in drawerLinks4"
            :key="link.label"
            clickable
            v-ripple
            @click="link.action"
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
        </q-list>
      </q-scroll-area>
      <div v-if="$q.screen.gt.sm" class="absolute" style="top: 15px; right: -17px">
        <MiniStateButton :drawer-mini-state="drawerMiniState" @click="miniStateClick" />
      </div>
    </q-drawer>
    <RightSidebar />
    <q-page-container>
      <q-banner v-if="showSessionBanner" class="session-banner bg-amber-1 text-grey-9" role="status">
        <template #avatar><q-icon name="cloud_off" color="amber-9" /></template>
        Your previous sign-in is stored on this device, but the session cannot currently be
        verified: the server is unreachable or failing. Your data appears once it is verified.
        <template #action>
          <q-btn flat color="primary" label="Retry" :loading="retryingSession" @click="retrySession" />
          <q-btn flat color="primary" label="Sign out" @click="handleLogout" />
        </template>
      </q-banner>
      <QuotaBanner @login="showLogin = true" @register="showRegister = true" />
      <router-view />
    </q-page-container>

    <LoginDialog v-model="showLogin" />
    <RegisterDialog v-model="showRegister" />
    <UserInfoDialog v-model="showUserInfo" />
    <AboutAppDialog v-model="showAbout" />
  </q-layout>
</template>

<script setup lang="ts">
import MiniStateButton from './MiniStateButton.vue'
import semantLogo from 'src/assets/semant-logo.png'
import { computed, ref, onMounted, watch } from 'vue'
import { useQuasar } from 'quasar'
import { useUserStore } from 'src/features/auth/userStore'
import { useRightSidebarStore } from 'src/app/sidebar/rightSidebarStore'
import RightSidebar from 'src/app/sidebar/RightSidebar.vue'
import LoginDialog from 'src/features/auth/LoginDialog.vue'
import RegisterDialog from 'src/features/auth/RegisterDialog.vue'
import UserInfoDialog from 'src/features/auth/UserInfoDialog.vue'
import AboutAppDialog from './AboutAppDialog.vue'
import QuotaIndicator from 'src/features/quota/QuotaIndicator.vue'
import QuotaBanner from 'src/features/quota/QuotaBanner.vue'
import { errorStatus } from 'src/shared/api'

const drawerMiniState = ref(false)

const userStore = useUserStore()
const rightSidebar = useRightSidebarStore()
const $q = useQuasar()

const leftDrawerOpen = ref(true)
const showLogin = ref(false)
const showRegister = ref(false)
const showUserInfo = ref(false)
const showAbout = ref(false)
// Signing out replaces the menu's items at once, before v-close-popup can close it.
const userMenuOpen = ref(false)

onMounted(async () => {
  // Restore session if a token exists in localStorage
  await userStore.restoreSession()
})

interface DrawerAction {
  label: string
  icon: string
  action: () => void
}

// Navigation follows the session: protected pages and account actions only when signed
// in, Log in / Register only when signed out. The backend still authorizes every request.
const drawerLinks1 = computed(() => [
  { label: 'Document search', icon: 'search', to: { name: 'search' } },
  { label: 'Chat Assistant', icon: 'chat', to: { name: 'rag' } },
  { label: 'Corpus', icon: 'insights', to: { name: 'corpus' } },
  ...(userStore.isLoggedIn ? [{ label: 'Collections', icon: 'folder', to: { name: 'collections' } }] : []),
  { label: 'About', icon: 'info', to: { name: 'about' } }
])

// Account settings live in the account dialog; there is no settings page.
const drawerLinks2 = computed<DrawerAction[]>(() => userStore.isLoggedIn
  ? [{ label: 'Settings', icon: 'settings', action: () => { showUserInfo.value = true } }]
  : [])

const drawerLinks3 = [
  { label: 'Send feedback', icon: '', to: { name: 'feedback' } }
]

// A session awaiting verification is not signed out: Sign out, no Log in / Register.
const drawerLinks4 = computed<DrawerAction[]>(() => userStore.isLoggedIn || userStore.awaitingVerification
  ? [{ label: 'Sign out', icon: 'logout', action: handleLogout }]
  : [
      { label: 'Log in', icon: 'login', action: () => { showLogin.value = true } },
      { label: 'Register', icon: 'person_add', action: () => { showRegister.value = true } }
    ])

function toggleLeftDrawer () {
  leftDrawerOpen.value = !leftDrawerOpen.value
}

// Account dialogs belong to one session: signing out, an expired session or another
// account (also from another tab) closes them; a sign-in elsewhere closes Log in / Register.
watch(() => userStore.getUserId, (userId, previousUserId) => {
  if (previousUserId && userId !== previousUserId) showUserInfo.value = false
})
watch(() => userStore.isLoggedIn, (loggedIn) => {
  if (!loggedIn) return
  showLogin.value = false
  showRegister.value = false
})

// A stored session the server could not verify (offline, server error) is neither signed in
// nor out: the banner says so and offers Retry and Sign out until it is verified or ends.
const retryingSession = ref(false)
const showSessionBanner = computed(() => userStore.awaitingVerification && (userStore.restoreFailed || retryingSession.value))

async function retrySession () {
  retryingSession.value = true
  try {
    await userStore.restoreSession({ retry: true })
  } finally {
    retryingSession.value = false
  }
}

// Signing out ends the session here at once (userStore.logout), so the signed-out UI never
// waits for the server. The backend's JWT logout revokes nothing; when it fails (offline,
// server error) the user is also told the server did not confirm it, without an unhandled
// rejection. A request that never answers simply never adds that warning.
function handleLogout () {
  userMenuOpen.value = false
  const confirmation = userStore.logout()
  $q.notify({ type: 'info', message: 'You have been logged out.', position: 'top', timeout: 3000 })
  confirmation.catch((error: unknown) => {
    // 401: the server no longer accepted the token, so nothing is left to confirm. A session
    // signed in meanwhile (here or in another tab) is not the one this warning is about.
    if (errorStatus(error) === 401 || userStore.token) return
    $q.notify({
      type: 'warning',
      message: 'The server could not confirm the sign-out. You remain logged out on this device.',
      position: 'top',
      timeout: 5000
    })
  })
}
const miniStateClick = () => {
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

.toolbar-logo {
  height: 36px;
  width: auto;
}

@media screen and (max-width: 600px) {
  .toolbar-title {
    display: none;
  }
}

/*&:hover
     color: #000*/
</style>
