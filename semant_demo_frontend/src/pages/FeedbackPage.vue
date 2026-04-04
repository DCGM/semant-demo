<template>
  <q-page class="q-pt-md">
    <PageTitle title="Feedback" />

    <div class="q-px-md q-pb-lg">
      <q-card flat bordered class="feedback-card">
        <q-card-section>
          <div class="text-h6 text-weight-medium">Send Us Your Feedback</div>
          <div class="text-body2 text-grey-7 q-mt-xs">
            Tell us what works well and what we should improve.
          </div>
        </q-card-section>

        <q-separator />

        <q-form ref="feedbackForm" @submit.prevent="submitFeedback" @reset="resetForm">
          <q-card-section class="column q-gutter-md">
            <q-select
              v-model="form.type"
              :options="feedbackTypeOptions"
              label="Feedback Type"
              outlined
              dense
              emit-value
              map-options
            />

            <q-input
              v-model.trim="form.subject"
              label="Subject"
              outlined
              dense
              maxlength="120"
            />

            <q-input
              v-model.trim="form.message"
              label="Message"
              outlined
              type="textarea"
              autogrow
              counter
              lazy-rules
              :rules="[(value) => !!value || 'Message is required']"
            />

            <q-input
              v-model.trim="form.email"
              label="Your Email (optional)"
              outlined
              dense
              type="email"
              lazy-rules
              :rules="[
                (value) =>
                  !value || /.+@.+\..+/.test(value) || 'Enter a valid email'
              ]"
            />
          </q-card-section>

          <q-card-actions align="right" class="q-px-md q-pb-md">
            <q-btn
              flat
              label="Reset"
              color="grey-7"
              :disable="isSubmitting"
              type="reset"
            />
            <q-btn
              unelevated
              color="primary"
              label="Send Feedback"
              type="submit"
              :loading="isSubmitting"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useQuasar } from 'quasar'
import axios from 'axios'
import PageTitle from 'src/components/custom/PageTitle.vue'

type FeedbackType = 'general' | 'bug' | 'feature'

interface FeedbackForm {
  type: FeedbackType
  subject: string | null
  message: string | null
  email: string | null
}

const $q = useQuasar()
const feedbackForm = ref()
const isSubmitting = ref(false)
const backendUrl = process.env.BACKEND_URL || 'http://pcvaskom.fit.vutbr.cz:8024'

const feedbackTypeOptions = [
  { label: 'General', value: 'general' },
  { label: 'Bug Report', value: 'bug' },
  { label: 'Feature Request', value: 'feature' }
]

const form = reactive<FeedbackForm>({
  type: 'general',
  subject: null,
  message: null,
  email: null
})

const resetForm = () => {
  form.type = 'general'
  form.subject = null
  form.message = null
  form.email = null
  feedbackForm.value?.resetValidation()
}

const submitFeedback = async () => {
  if (!form.message) {
    return
  }

  isSubmitting.value = true

  try {
    await axios.post(`${backendUrl}/api/feedback`, {
      type: form.type,
      subject: form.subject || null,
      message: form.message,
      email: form.email || null
    })

    $q.notify({
      type: 'positive',
      message: 'Thank you. Your feedback was sent.'
    })

    resetForm()
  } catch {
    $q.notify({
      type: 'negative',
      message: 'Failed to deliver feedback to developers. Please try again.'
    })
  } finally {
    isSubmitting.value = false
  }
}
</script>

<style scoped>
.feedback-card {
  max-width: 900px;
  margin: 0 auto;
}
</style>
