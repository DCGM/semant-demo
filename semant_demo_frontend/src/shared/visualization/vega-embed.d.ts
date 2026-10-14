/**
 * The part of vega-embed that `VegaChart.vue` uses. The Vega packages declare their types
 * only through `package.json` `exports`, which the project's `moduleResolution: "node"`
 * (Quasar's preset) does not read; widen this when more of the API is needed.
 */
declare module 'vega-embed' {
  /** A Vega-Lite or Vega specification (JSON). */
  export type VisualizationSpec = Record<string, unknown>

  export interface EmbedOptions {
    actions?: boolean
    renderer?: 'svg' | 'canvas'
  }

  export interface Result {
    finalize (): void
  }

  export default function embed (element: HTMLElement | string, spec: VisualizationSpec | string,
    options?: EmbedOptions): Promise<Result>
}
