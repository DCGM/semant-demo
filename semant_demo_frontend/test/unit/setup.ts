// jsdom does not lay out pages, and its window.scrollTo only reports "Not implemented" with a
// stack trace (Quasar calls it when a dialog locks the page scroll). Nothing here scrolls.
// Specs in the node environment (devTooling) have no window.
if (typeof window !== 'undefined') window.scrollTo = () => undefined
