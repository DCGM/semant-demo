<template>
  <q-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" persistent>
    <q-card style="min-width: 360px">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6">Log In</div>
        <q-space />
        <q-btn icon="close" flat round dense v-close-popup />
      </q-card-section>

      <q-card-section>
        <q-form @submit.prevent="submit" class="q-gutter-md">
          <q-input
            v-model="email"
            label="Email or Username"
            outlined
            dense
            lazy-rules
            :rules="[v => !!v || 'Email or username is required']"
          />
          <q-input
            v-model="password"
            label="Password"
            :type="showPassword ? 'text' : 'password'"
            outlined
            dense
            lazy-rules
            :rules="[v => !!v || 'Password is required']"
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

          <div class="row justify-center q-mt-md">
            <q-btn type="submit" label="Log In" color="primary" :loading="loading" style="min-width: 120px" />
          </div>
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

const userStore = useUserStore()

async function submit() {
  errorMsg.value = ''
  loading.value = true
  try {
    await userStore.login(email.value, password.value)
    show.value = false
    email.value = ''
    password.value = ''
  } catch (e: unknown) {
    errorMsg.value = 'Invalid email or password.'
  } finally {
    loading.value = false
  }
}
</script>
