// Display types for annotation badges. API types come from the generated client
// (src/generated/api).

export enum ApprovedState {
  automatic = 'automatic',
  positive = 'positive',
  negative = 'negative',
}

export interface AnnotationClass {
  short: string
  colorString: string
  textColor: string
}

export interface ExtendedAnnotationClass {
  short: string
  colorString: string
  textColor: string
  approved: ApprovedState
}
