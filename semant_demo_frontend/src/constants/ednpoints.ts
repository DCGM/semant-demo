const ENDPOINTS = {
  COLLECTIONS: 'v1/collections'
} as const

type Endpoint = typeof ENDPOINTS[keyof typeof ENDPOINTS];

export { ENDPOINTS }
export type { Endpoint }
