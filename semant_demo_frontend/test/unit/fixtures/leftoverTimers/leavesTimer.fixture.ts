import { afterAll, it } from 'vitest'

// Quasar notifications removing themselves and animation steps still waiting after the file
// ended, in miniature. Each one uses the page when it runs.
it('leaves a timeout, an interval and an animation frame that use the page', () => {
  setTimeout(() => document.title, 50)
  setInterval(() => document.title, 20)
  requestAnimationFrame(() => getComputedStyle(document.body))
})

// Created after the last test, as by an unmount or a late notification.
afterAll(() => {
  setTimeout(() => document.title, 50)
})
