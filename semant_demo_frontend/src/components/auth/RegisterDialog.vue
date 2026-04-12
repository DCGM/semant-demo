<template>
  <q-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" persistent>
    <q-card style="min-width: 360px">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6">Create Account</div>
        <q-space />
        <q-btn icon="close" flat round dense v-close-popup />
      </q-card-section>

      <q-card-section>
        <q-form @submit.prevent="submit" class="q-gutter-md">
          <q-input
            v-model="email"
            label="Email"
            type="email"
            outlined
            dense
            :rules="[v => !!v || 'Email is required']"
          />
          <q-input
            v-model="password"
            label="Password"
            :type="showPassword ? 'text' : 'password'"
            outlined
            dense
            :rules="[v => v.length >= 8 || 'Minimum 8 characters']"
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
            label="Register"
            color="primary"
            class="full-width"
            :loading="loading"
          />
        </q-form>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useUserStore } from 'src/stores/user-store'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits(['update:modelValue'])

const show = computed({ get: () => props.modelValue, set: (v: boolean) => emit('update:modelValue', v) })

const email = ref('')
const password = ref('')
const showPassword = ref(false)
const loading = ref(false)
const errorMsg = ref('')
const successMsg = ref('')

const userStore = useUserStore()

async function submit() {
  errorMsg.value = ''
  successMsg.value = ''
  loading.value = true
  try {
    await userStore.register(email.value, password.value)
    successMsg.value = 'Account created! You can now log in.'
    email.value = ''
    password.value = ''
  } catch (e: unknown) {
    errorMsg.value = 'Registration failed. The email may already be in use.'
  } finally {
    loading.value = false
  }
}
</script>
