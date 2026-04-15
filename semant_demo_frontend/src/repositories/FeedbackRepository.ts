import { Feedback } from 'src/models/feedback'
import { FeedbackSchema } from 'src/schemas/feedback'
import FeedbackService from 'src/services/FeedbackService'

const FeedbackRepository = {
  submit: async (feedback: Feedback): Promise<void> => {
    const parsedData = FeedbackSchema.safeParse(feedback)

    if (!parsedData.success) {
      throw new Error('Invalid feedback data')
    }

    await FeedbackService.submit(parsedData.data)
  }
}

export default FeedbackRepository
