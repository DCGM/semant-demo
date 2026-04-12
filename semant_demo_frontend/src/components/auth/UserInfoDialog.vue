<template>
  <q-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)">
    <q-card style="min-width: 380px">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6">User Information</div>
        <q-space />
        <q-btn icon="close" flat round dense v-close-popup />
      </q-card-section>

      <q-card-section class="q-gutter-sm">
        <div><span class="text-weight-bold">Email:</span> {{ user?.email }}</div>
        <div><span class="text-weight-bold">Username:</span> {{ user?.username || '—' }}</div>
        <div><span class="text-weight-bold">User ID:</span> {{ user?.id }}</div>
      </q-card-section>

      <q-separator />

      <!-- Edit profile -->
      <q-card-section>
        <div class="text-subtitle2 q-mb-sm">Edit Profile</div>
        <q-form ref="profileFormRef" @submit.prevent="saveProfile" class="q-gutter-md">
          <q-input
            v-model="editName"
            label="Name"
            outlined
            dense
            lazy-rules
            :rules="[v => !!v || 'Name is required']"
          />
          <q-input
            v-model="editInstitution"
            label="Institution (optional)"
            outlined
            dense
          />
          <div v-if="profileErrorMsg" class="text-negative text-caption">{{ profileErrorMsg }}</div>
          <div v-if="profileSuccessMsg" class="text-positive text-caption">{{ profileSuccessMsg }}</div>
          <div class="row justify-center">
            <q-btn type="submit" label="Save Profile" color="primary" :loading="profileLoading" style="min-width: 130px" />
          </div>
        </q-form>
      </q-card-section>

      <q-separator />

      <!-- Change password -->
      <q-card-section>
        <div class="text-subtitle2 q-mb-sm">Change Password</div>
        <q-form ref="passwordFormRef" @submit.prevent="changePassword" class="q-gutter-md">
          <q-input
            v-model="newPassword"
            label="New Password"
            :type="showPassword ? 'text' : 'password'"
            outlined
            dense
            lazy-rules
            :rules="[v => !!v || 'Password is required', v => v.length >= 8 || 'Minimum 8 characters']"
          >
            <template #append>
              <q-icon
                :name="showPassword ? 'visibility_off' : 'visibility'"
                class="cursor-pointer"
                @click="showPassword = !showPassword"
              />
            </template>
          </q-input>
          <q-input
            v-model="confirmPassword"
            label="Confirm New Password"
            :type="showPassword ? 'text' : 'password'"
            outlined
            dense
            lazy-rules
            :rules="[v => !!v || 'Please confirm your password', v => v === newPassword || 'Passwords do not match']"
          />

          <div v-if="passwordErrorMsg" class="text-negative text-caption">{{ passwordErrorMsg }}</div>
          <div v-if="passwordSuccessMsg" class="text-positive text-caption">{{ passwordSuccessMsg }}</div>

          <div class="row justify-center">
            <q-btn type="submit" label="Update Password" color="primary" :loading="passwordLoading" style="min-width: 150px" />
          </div>
        </q-form>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { QForm } from 'quasar'
import { useUserStore } from 'src/stores/user-store'
import { storeToRefs } from 'pinia'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits(['update:modelValue'])

const userStore = useUserStore()
const { user } = storeToRefs(userStore)

// Profile section
const profileFormRef = ref<QForm | null>(null)
const editName = ref(user.value?.name ?? '')
const editInstitution = ref(user.value?.institution ?? '')
const profileLoading = ref(false)
const profileErrorMsg = ref('')
const profileSuccessMsg = ref('')

// Sync fields when dialog opens
watch(() => props.modelValue, (open) => {
  if (open) {
    editName.value = user.value?.name ?? ''
    editInstitution.value = user.value?.institution ?? ''
    profileFormRef.value?.resetValidation()
    passwordFormRef.value?.resetValidation()
    newPassword.value = ''
    confirmPassword.value = ''
    profileErrorMsg.value = ''
    profileSuccessMsg.value = ''
    passwordErrorMsg.value = ''
    passwordSuccessMsg.value = ''
  }
})

async function saveProfile() {
  const valid = await profileFormRef.value?.validate()
  if (!valid) return
  profileErrorMsg.value = ''
  profileSuccessMsg.value = ''
  profileLoading.value = true
  try {
    await userStore.updateUser({ name: editName.value, institution: editInstitution.value || null })
    profileSuccessMsg.value = 'Profile updated successfully.'
  } catch {
    profileErrorMsg.value = 'Failed to update profile.'
  } finally {
    profileLoading.value = false
  }
}

// Password section
const passwordFormRef = ref<QForm | null>(null)
const newPassword = ref('')
const confirmPassword = ref('')
const showPassword = ref(false)
const passwordLoading = ref(false)
const passwordErrorMsg = ref('')
const passwordSuccessMsg = ref('')

async function changePassword() {
  const valid = await passwordFormRef.value?.validate()
  if (!valid) return
  passwordErrorMsg.value = ''
  passwordSuccessMsg.value = ''
  passwordLoading.value = true
  try {
    await userStore.updateUser({ password: newPassword.value })
    passwordSuccessMsg.value = 'Password updated successfully.'
    newPassword.value = ''
    confirmPassword.value = ''
    passwordFormRef.value?.resetValidation()
  } catch {
    passwordErrorMsg.value = 'Failed to update password.'
  } finally {
    passwordLoading.value = false
  }
}
</script>
