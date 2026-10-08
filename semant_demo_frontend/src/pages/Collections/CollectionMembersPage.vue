<template>
  <div class="collection-members q-pa-md">
    <q-card v-if="rights.share" flat bordered class="panel-card q-mb-lg">
      <q-card-section class="q-pb-sm">
        <div class="text-subtitle1 text-weight-medium">Share with a user</div>
        <div class="panel-subtitle">Search by username or name</div>
      </q-card-section>

      <q-card-section class="q-pt-none">
        <q-input
          v-model="searchQuery"
          outlined
          dense
          debounce="300"
          placeholder="Search users..."
          clearable
          @clear="searchQuery = ''"
        >
          <template #prepend>
            <q-icon name="search" />
          </template>
        </q-input>

        <div v-if="showMinLengthHint" class="search-hint">Type at least 3 characters to search.</div>

        <q-list v-if="searchResults.length" separator class="q-mt-sm">
          <q-item v-for="user in searchResults" :key="user.id">
            <q-item-section avatar>
              <q-avatar color="secondary" text-color="white">
                {{ initials(user) }}
              </q-avatar>
            </q-item-section>
            <q-item-section>
              <q-item-label>{{ displayName(user) }}</q-item-label>
              <q-item-label v-if="user.username" caption>@{{ user.username }}</q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-btn
                flat
                dense
                :disable="isAlreadyShared(user)"
                :loading="actingUserId === user.id"
                :label="isAlreadyShared(user) ? 'Shared' : 'Share'"
                color="primary"
                @click="shareWith(user)"
              />
            </q-item-section>
          </q-item>
        </q-list>
        <div v-else-if="searchAttempted && !searchLoading" class="empty-state">No matching users found.</div>

        <q-inner-loading :showing="searchLoading" />
      </q-card-section>
    </q-card>

    <q-card flat bordered class="panel-card">
      <q-card-section class="q-pb-sm">
        <div class="text-subtitle1 text-weight-medium">Shared with</div>
      </q-card-section>

      <q-card-section class="q-pt-none">
        <q-list v-if="sharedUsers.length" separator>
          <q-item v-for="user in sharedUsers" :key="user.id">
            <q-item-section avatar>
              <q-avatar color="primary" text-color="white">
                {{ initials(user) }}
              </q-avatar>
            </q-item-section>
            <q-item-section>
              <q-item-label>{{ displayName(user) }}</q-item-label>
              <q-item-label v-if="user.username" caption>@{{ user.username }}</q-item-label>
            </q-item-section>
            <q-item-section v-if="rights.share" side>
              <q-btn
                flat
                dense
                round
                icon="person_remove"
                aria-label="Cancel share"
                color="negative"
                :loading="actingUserId === user.id"
                @click="cancelShare(user)"
              >
                <q-tooltip>Cancel share</q-tooltip>
              </q-btn>
            </q-item-section>
          </q-item>
        </q-list>
        <div v-else class="empty-state">This collection is not shared with anyone yet.</div>

        <ErrorDisplay :error="membersError" />
        <q-inner-loading :showing="membersLoading" />
      </q-card-section>
    </q-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useUserRepository } from 'src/repositories/useUserRepository'
import { useCollectionRepository } from 'src/repositories/useCollectionRepository'
import { useUserStore } from 'src/stores/user-store'
import { UserSearchResult } from 'src/generated/api'
import ErrorDisplay from 'src/components/custom/ErrorDisplay.vue'
import useCollections from 'src/composables/useCollections'
import { collectionRights } from 'src/features/collections/permissions'
import { createContextGuard } from 'src/shared/api'

const $route = useRoute()
const userRepository = useUserRepository()
const collectionRepository = useCollectionRepository()
const userStore = useUserStore()

const collectionId = computed(() => {
  const value = $route.params.collectionId
  return typeof value === 'string' ? value : ''
})

// Shared users see the member list but only the owner shares and unshares (ADR 0007).
// The collection is loaded by the enclosing CollectionDetailLayout.
const { activeCollection } = useCollections()
const rights = computed(() =>
  collectionRights(activeCollection.value?.id === collectionId.value ? activeCollection.value : null)
)

const sharedUsers = ref<UserSearchResult[]>([])
const membersLoading = ref(false)
const membersError = ref<string | null>(null)
const actingUserId = ref<string | null>(null)

const searchQuery = ref('')
const searchResults = ref<UserSearchResult[]>([])
const searchLoading = ref(false)
const searchAttempted = ref(false)

const MIN_SEARCH_LENGTH = 3

const showMinLengthHint = computed(() =>
  searchQuery.value.trim().length > 0 && searchQuery.value.trim().length < MIN_SEARCH_LENGTH
)

const displayName = (user: UserSearchResult) => user.name || user.username || 'Unknown user'

const initials = (user: UserSearchResult) => {
  const name = displayName(user)
  const parts = name.trim().split(' ')
  if (parts[0] && parts[1]) {
    return (parts[0][0] ?? '') + (parts[1][0] ?? '')
  }
  return parts[0]?.[0] ?? ''
}

const isAlreadyShared = (user: UserSearchResult) =>
  sharedUsers.value.some((shared) => shared.id === user.id)

// Answers for an earlier collection or an earlier search query are dropped.
const membersGuard = createContextGuard()
const searchGuard = createContextGuard()

const loadMembers = async () => {
  if (!collectionId.value) return
  membersGuard.enter()
  const isCurrent = membersGuard.capture()
  membersLoading.value = true
  membersError.value = null
  try {
    const members = await collectionRepository.getMembers(collectionId.value)
    if (isCurrent()) sharedUsers.value = members
  } catch (err) {
    if (!isCurrent()) return
    membersError.value = 'Failed to load shared users'
    console.error('Error fetching collection members:', err)
  } finally {
    if (isCurrent()) membersLoading.value = false
  }
}

const shareWith = async (user: UserSearchResult) => {
  if (isAlreadyShared(user) || !collectionId.value) return
  actingUserId.value = user.id
  membersError.value = null
  try {
    await collectionRepository.share(collectionId.value, user.id)
    await loadMembers()
  } catch (err) {
    membersError.value = 'Failed to share collection'
    console.error('Error sharing collection:', err)
  } finally {
    actingUserId.value = null
  }
}

const cancelShare = async (user: UserSearchResult) => {
  if (!collectionId.value) return
  actingUserId.value = user.id
  membersError.value = null
  try {
    await collectionRepository.unshare(collectionId.value, user.id)
    await loadMembers()
  } catch (err) {
    membersError.value = 'Failed to cancel share'
    console.error('Error cancelling collection share:', err)
  } finally {
    actingUserId.value = null
  }
}

watch(searchQuery, async (query) => {
  searchGuard.enter()
  const isCurrent = searchGuard.capture()
  const trimmed = query.trim()
  if (trimmed.length < MIN_SEARCH_LENGTH) {
    searchResults.value = []
    searchAttempted.value = false
    searchLoading.value = false
    return
  }

  searchLoading.value = true
  searchAttempted.value = false
  try {
    const results = await userRepository.search(trimmed)
    if (isCurrent()) searchResults.value = results.filter((user) => user.id !== userStore.getUserId)
  } finally {
    if (isCurrent()) {
      searchLoading.value = false
      searchAttempted.value = true
    }
  }
})

watch(collectionId, () => {
  sharedUsers.value = []
  void loadMembers()
})

onMounted(() => {
  loadMembers()
})
</script>

<style scoped lang="scss">
.collection-members {
  width: 100%;
}

.panel-card {
  border-radius: 12px;
}

.panel-card > .q-card__section:first-child .text-subtitle1 {
  font-size: 1.1rem;
  font-weight: 700;
  color: #1f2a37;
}

.panel-subtitle {
  color: #758195;
  font-size: 0.9rem;
}

.empty-state {
  color: #758195;
  font-size: 0.9rem;
  padding: 12px 0;
}

.search-hint {
  color: #758195;
  font-size: 0.85rem;
  margin-top: 6px;
}
</style>
