import createClient, { type Middleware } from 'openapi-fetch'
import type { paths } from './schema'

const TOKEN_KEY = 'cc-token'

export const auth = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

const authMiddleware: Middleware = {
  onRequest({ request }) {
    const token = auth.get()
    if (token) request.headers.set('Authorization', `Bearer ${token}`)
    return request
  },
}

export const api = createClient<paths>({ baseUrl: '/' })
api.use(authMiddleware)

/** Unwrap an openapi-fetch result, throwing ApiError on failure. */
export async function unwrap<T>(
  promise: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await promise
  if (error !== undefined || !response.ok) {
    const detail = (error as { detail?: unknown })?.detail
    throw new ApiError(response.status, typeof detail === 'string' ? detail : response.statusText)
  }
  return data as T
}
