<template>
  <q-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" persistent>
    <q-card style="min-width: 380px">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6">Create Account</div>
        <q-space />
        <q-btn icon="close" flat round dense v-close-popup @click="resetForm" />
      </q-card-section>

      <q-card-section>
        <q-form ref="formRef" @submit.prevent="submit" class="q-gutter-md">
          <q-input
            v-model="username"
            label="Username"
            outlined
            dense
            lazy-rules
            :rules="[v => !!v || 'Username is required', v => v.length >= 3 || 'Minimum 3 characters']"
          />
          <q-input
            v-model="name"
            label="Name"
            outlined
            dense
            lazy-rules
            :rules="[v => !!v || 'Name is required']"
          />
          <q-input
            v-model="institution"
            label="Institution (optional)"
            outlined
            dense
          />
          <q-input
            v-model="email"
            label="Email"
            type="email"
            outlined
            dense
            lazy-rules
            :rules="[v => !!v || 'Email is required', v => /.+@.+\..+/.test(v) || 'Enter a valid email']"
          />
          <q-input
            v-model="password"
            label="Password"
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
            label="Confirm Password"
            :type="showPassword ? 'text' : 'password'"
            outlined
            dense
            lazy-rules
            :rules="[v => !!v || 'Please confirm your password', v => v === password || 'Passwords do not match']"
          />

          <div v-if="errorMsg" class="text-negative text-caption">{{ errorMsg }}</div>

          <div class="row justify-evenly q-mt-md">
            <q-btn flat label="Cancel" color="primary" v-close-popup @click="resetForm" />
            <q-btn type="submit" label="Register" color="primary" :loading="loading" />
          </div>
        </q-form>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { QForm } from 'quasar'
import { useQuasar } from 'quasar'
import { useUserStore } from 'src/stores/user-store'

const emit = defineEmits(['update:modelValue'])

const $q = useQuasar()
const formRef = ref<QForm | null>(null)
const username = ref('')
const name = ref('')
const institution = ref('')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const showPassword = ref(false)
const loading = ref(false)
const errorMsg = ref('')

const userStore = useUserStore()

function resetForm() {
  username.value = ''
  name.value = ''
  institution.value = ''
  email.value = ''
  password.value = ''
  confirmPassword.value = ''
  errorMsg.value = ''
  formRef.value?.resetValidation()
}

async function submit() {
  const valid = await formRef.value?.validate()
  if (!valid) return

  errorMsg.value = ''
  loading.value = true
  try {
    await userStore.register(email.value, password.value, username.value, name.value, institution.value || undefined)
    resetForm()
    emit('update:modelValue', false)
    $q.notify({
      type: 'positive',
      message: 'Account created! You can now log in.',
      position: 'top',
      timeout: 4000
    })
  } catch (e: unknown) {
    errorMsg.value = 'Registration failed. The email or username may already be in use.'
  } finally {
    loading.value = false
  }
}
</script>
