const logError = (error: unknown, context?: string) => {
  if (error instanceof Error) {
    console.error(`Error${context ? ` in ${context}` : ''}:`, error.message)
  } else {
    console.error(`Unknown error${context ? ` in ${context}` : ''}:`, error)
  }
}

export default logError
