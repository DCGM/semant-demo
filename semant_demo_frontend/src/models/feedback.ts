import { z } from 'zod'

import { FeedbackSchema } from 'src/schemas/feedback'

export type Feedback = z.infer<typeof FeedbackSchema>
