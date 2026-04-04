import { api } from 'src/boot/axios'
import { ENDPOINTS } from 'src/constants/endpoints'
import type { Feedback } from 'src/models/feedback'

const FeedbackService = {
  submit: async (feedback: Feedback) =>
    await api.post(ENDPOINTS.FEEDBACK, {
      type: feedback.type,
      subject: feedback.subject || null,
      message: feedback.message,
      email: feedback.email || null
    })
}

export default FeedbackService
