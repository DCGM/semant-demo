import { Feedback } from 'src/models/feedback'
import { FeedbackSchema } from 'src/schemas/feedback'
import { useApi } from 'src/shared/api'

const FeedbackRepository = {
  submit: async (feedback: Feedback): Promise<void> => {
    const parsedData = FeedbackSchema.safeParse(feedback)

    if (!parsedData.success) {
      throw new Error('Invalid feedback data')
    }

    const { type, subject, message, email } = parsedData.data
    await useApi().default.saveAppFeedbackApiV1FeedbackPost({
      appFeedbackRequest: { type, subject: subject || null, message, email: email || null }
    })
  }
}

export default FeedbackRepository
