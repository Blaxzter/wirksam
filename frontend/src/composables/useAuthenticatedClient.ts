import { useSidebarStore } from '@/stores/sidebar'

import { client } from '@/client/client.gen'
import type { Auth } from '@/client/core/auth.gen'
import { authSession } from '@/lib/auth-session'

type HttpVerb = 'get' | 'post' | 'put' | 'delete' | 'patch'

// Mutations on these resource paths change what the sidebar shows
// (tasks, my bookings, open-shift counts, event list).
const SIDEBAR_AFFECTING_PATH = /\/(bookings|tasks|shifts|events)(\/|$|\?)/
// ...except vouchers, which live under /events/ but change nothing the sidebar
// shows. Without this, every new code (one every two minutes while it is on
// screen) and every redemption at a stand would refetch it.
const SIDEBAR_IGNORED_PATH = /\/vouchers(\/|$|\?)/

/**
 * Composable for making authenticated API calls
 * Uses the built-in security mechanism of the generated client
 */
export function useAuthenticatedClient() {
  /**
   * The bearer token for the next request.
   *
   * Read straight from the session module rather than from the auth store:
   * `stores/auth.ts` constructs this composable, so reaching back into the
   * store would close an import cycle. The module re-mints an access token that
   * is about to lapse behind this call, which is why it is awaited per request
   * instead of captured once.
   */
  const getAuthToken = async () => {
    const token = await authSession.getAccessToken()
    if (!token) {
      throw new Error('User is not authenticated')
    }
    return token
  }

  /**
   * Auth configuration for Bearer token
   */
  const bearerAuth: Auth = {
    type: 'http',
    scheme: 'bearer',
    in: 'header',
    name: 'Authorization',
  }

  /**
   * Auth callback that returns the token
   */
  const authCallback = async () => {
    return await getAuthToken()
  }

  /**
   * Generic authenticated request function
   */
  const makeAuthenticatedRequest = async <T, M extends HttpVerb>(
    method: M,
    options: Parameters<(typeof client)[M]>[0],
  ): Promise<T> => {
    type ClientMethodOptions = Parameters<(typeof client)[M]>[0]
    const clientMethod = client[method] as (opts: ClientMethodOptions) => Promise<T>

    const requestOptions: ClientMethodOptions =
      typeof options === 'string'
        ? ({ url: options, security: [bearerAuth], auth: authCallback } as ClientMethodOptions)
        : ({ ...options, security: [bearerAuth], auth: authCallback } as ClientMethodOptions)

    const result = await clientMethod(requestOptions)

    if (method !== 'get') {
      const url = typeof options === 'string' ? options : (options as { url?: string }).url
      if (url && SIDEBAR_AFFECTING_PATH.test(url) && !SIDEBAR_IGNORED_PATH.test(url)) {
        useSidebarStore().refresh()
      }
    }

    return result
  }

  /**
   * HTTP method shortcuts with proper generic type support
   * Usage: await get<{ data: { items: UserProfile[] } }>({ url: '/users/' })
   */
  const get = async <T>(options: Parameters<typeof client.get>[0]): Promise<T> =>
    makeAuthenticatedRequest<T, 'get'>('get', options)

  const post = async <T>(options: Parameters<typeof client.post>[0]): Promise<T> =>
    makeAuthenticatedRequest<T, 'post'>('post', options)

  const put = async <T>(options: Parameters<typeof client.put>[0]): Promise<T> =>
    makeAuthenticatedRequest<T, 'put'>('put', options)

  const del = async <T = void>(options: Parameters<typeof client.delete>[0]): Promise<T> =>
    makeAuthenticatedRequest<T, 'delete'>('delete', options)

  const patch = async <T>(options: Parameters<typeof client.patch>[0]): Promise<T> =>
    makeAuthenticatedRequest<T, 'patch'>('patch', options)

  return {
    getAuthToken,
    makeAuthenticatedRequest,
    get,
    post,
    put,
    delete: del,
    patch,
  }
}
