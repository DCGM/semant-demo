<template>
  <q-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)">
    <q-card style="min-width: 360px">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6">User Information</div>
        <q-space />
        <q-btn icon="close" flat round dense v-close-popup />
      </q-card-section>

      <q-card-section class="q-gutter-sm">
        <div><span class="text-weight-bold">Email:</span> {{ user?.email }}</div>
        <div><span class="text-weight-bold">User ID:</span> {{ user?.id }}</div>
        <div><span class="text-weight-bold">Active:</span> {{ user?.is_active ? 'Yes' : 'No' }}</div>
      </q-card-section>

      <q-separator />

      <q-card-section>
        <div class="text-subtitle2 q-mb-sm">Change Password</div>
        <q-form @submit.prevent="changePassword" class="q-gutter-md">
          <q-input
            v-model="newPassword"
            label="New Password"
            :type="showPassword ? 'text' : 'password'"
            outlined
            dense
            :rules="[v => !v || v.length >= 8 || 'Minimum 8 characters']"
          >
            <template #append>
              <q-icon
                :name="showPassword ? 'visibility_off' : 'visibility'"
                class="cursor-pointer"
                @click="showPassword = !showPassword"
              />
            </template>
          </q-input>

          <div v-if="errorMsg" class="text-negative text-caption">{{ errorMsg }}</div>
          <div v-if="successMsg" class="text-positive text-caption">{{ successMsg }}</div>

          <q-btn
            type="submit"
            label="Update Password"
            color="primary"
            :loading="loading"
            :disable="!newPassword"
          />
        </q-form>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useUserStore } from 'src/stores/user-store'
import { storeToRefs } from 'pinia'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits(['update:modelValue'])

const show = computed({ get: () => props.modelValue, set: (v: boolean) => emit('update:modelValue', v) })

const userStore = useUserStore()
const { user } = storeToRefs(userStore)

const newPassword = ref('')
const showPassword = ref(false)
const loading = ref(false)
const errorMsg = ref('')
const successMsg = ref('')

async function changePassword() {
  errorMsg.value = ''
  successMsg.value = ''
  loading.value = true
  try {
    await userStore.updateUser({ password: newPassword.value })
    successMsg.value = 'Password updated successfully.'
    newPassword.value = ''
  } catch {
    errorMsg.value = 'Failed to update password.'
  } finally {
    loading.value = false
  }
}
</script>
