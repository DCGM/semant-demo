const ENDPOINTS = {
  COLLECTIONS: 'v1/collections',
  DOCUMENTS: 'v1/documents'
} as const

type Endpoint = typeof ENDPOINTS[keyof typeof ENDPOINTS];

export { ENDPOINTS }
export type { Endpoint }
