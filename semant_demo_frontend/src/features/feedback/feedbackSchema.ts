import { z } from 'zod'

const FeedbackSchema = z.object({
  type: z.enum(['general', 'bug', 'feature']),
  subject: z.string().nullable().optional(),
  message: z.string(),
  email: z.email().nullable().optional()
})

type Feedback = z.infer<typeof FeedbackSchema>

export { FeedbackSchema }
export type { Feedback }
