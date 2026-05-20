import { useCallback } from 'react'
import { useAuthContext } from '../context/auth'

export function useAuthFetch() {
  const { getToken } = useAuthContext()

  return useCallback(
    async (url: string, opts: RequestInit = {}): Promise<Response> => {
      const token = await getToken()
      return fetch(url, {
        ...opts,
        headers: {
          ...(opts.headers ?? {}),
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      })
    },
    [getToken],
  )
}
