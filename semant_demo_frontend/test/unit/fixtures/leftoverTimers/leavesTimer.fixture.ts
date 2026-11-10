import { it } from 'vitest'

// A Quasar notification removing itself after the file ended, in miniature.
it('leaves a timer that uses the page', () => {
  setTimeout(() => document.title, 50)
})
