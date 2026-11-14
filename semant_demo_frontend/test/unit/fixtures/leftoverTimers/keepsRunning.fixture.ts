import { it } from 'vitest'

// Keeps the run, and so the worker of the other file, alive past that file's timer.
it('keeps the run going', () => new Promise((resolve) => setTimeout(resolve, 1000)))
