import type embed from 'vega-embed'

/** vega-embed, loaded on first use so that Vega stays out of pages without charts. */
export async function loadEmbed (): Promise<typeof embed> {
  return (await import('vega-embed')).default
}
