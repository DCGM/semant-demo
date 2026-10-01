<template>
  <q-dialog ref="dialogRef" @hide="onDialogHide">
    <q-card class="q-pa-sm" style="width: 500px">
      <q-card-section>
        <div class="text-h6">Share {{ props.collectionCount }} collection{{ props.collectionCount === 1 ? '' : 's' }}</div>
        <div class="text-caption text-grey-7">Search for a user to share the selected collections with</div>
      </q-card-section>

      <q-card-section class="q-pt-none">
        <q-input
          v-model="searchQuery"
          autofocus
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
                label="Share"
                color="primary"
                @click="onDialogOK(user)"
              />
            </q-item-section>
          </q-item>
        </q-list>
        <div v-else-if="searchAttempted && !searchLoading" class="empty-state">No matching users found.</div>

        <q-inner-loading :showing="searchLoading" />
      </q-card-section>

      <q-card-actions align="right">
        <q-btn flat label="Cancel" color="primary" @click="onDialogCancel" />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDialogPluginComponent } from 'quasar'
import { ShareCollectionsDialogProps } from './ShareCollectionsDialogTypes'
import { useUserRepository } from 'src/repositories/useUserRepository'
import { useUserStore } from 'src/stores/user-store'
import { UserSearchResult } from 'src/generated/api'

const props = defineProps<ShareCollectionsDialogProps>()
const { dialogRef, onDialogHide, onDialogCancel, onDialogOK } = useDialogPluginComponent()
defineEmits([...useDialogPluginComponent.emits])

const userRepository = useUserRepository()
const userStore = useUserStore()

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

watch(searchQuery, async (query) => {
  const trimmed = query.trim()
  if (trimmed.length < MIN_SEARCH_LENGTH) {
    searchResults.value = []
    searchAttempted.value = false
    return
  }

  searchLoading.value = true
  searchAttempted.value = false
  try {
    const results = await userRepository.search(trimmed)
    searchResults.value = results.filter((user) => user.id !== userStore.getUserId)
  } finally {
    searchLoading.value = false
    searchAttempted.value = true
  }
})
</script>

<style scoped lang="scss">
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
