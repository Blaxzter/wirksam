// @vitest-environment jsdom
import { reactive } from 'vue'

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useSandboxStore } from '@/stores/sandbox'

import type { UserProfile } from '@/client/types.gen'
// The real module, not a mock: it imports nothing, it is the single owner of
// the storage key, and reading the flag back through its own `hasAutoStarted`
// is what proves the store cleared the thing `tour/install.ts` actually reads.
import { hasAutoStarted, markAutoStarted } from '@/tour/autostart'
// Likewise real: the store asks for the running tour to be put away through
// this module's window event, and the event name is the contract.
import { TOUR_STOP_EVENT } from '@/tour/offer'

/**
 * Everything the store reaches for is stubbed, because none of it is what the
 * store is *for*: the interesting behaviour is the order it does things in —
 * install the session, drop the stale profile, fetch the guest's own — and the
 * two re-entrancy guards that stop a double click minting two demos.
 *
 * The stubs are handed in through `vi.hoisted` holders rather than being built
 * in the mock factories, so each case can rebuild the auth store as a *reactive*
 * object. A plain object would let the computeds cache their first read and the
 * assertions would then be describing a stale snapshot.
 */
const holders = vi.hoisted(() => ({
  authStore: null as unknown as {
    profile: UserProfile | null
    selectedEventId: string | null
    ensureProfile: ReturnType<typeof vi.fn>
    eventRole: ReturnType<typeof vi.fn>
  },
  router: { push: vi.fn() },
  post: vi.fn(),
  del: vi.fn(),
  setSession: vi.fn(),
  clear: vi.fn(),
  toastApiError: vi.fn(),
  locale: { value: 'en' },
}))

vi.mock('@/stores/auth', () => ({ useAuthStore: () => holders.authStore }))
vi.mock('vue-router', () => ({ useRouter: () => holders.router }))
vi.mock('@/client/client.gen', () => ({ client: { post: holders.post } }))
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ delete: holders.del }),
}))
vi.mock('@/lib/auth-session', () => ({
  authSession: { setSession: holders.setSession, clear: holders.clear },
}))
vi.mock('@/lib/api-errors', () => ({ toastApiError: holders.toastApiError }))
vi.mock('@/locales/i18n', () => ({ default: { global: { locale: holders.locale } } }))

/** The guest profile `/users/me` answers with once the demo exists. */
const guestProfile = {
  id: 'guest-1',
  email: 'sandbox@example.invalid',
  is_sandbox: true,
  sandbox_expires_at: '2026-08-24T12:00:00Z',
} as UserProfile

/** What `POST /auth/sandbox` hands back — a login response, plus demo details. */
function sandboxResponse() {
  return {
    data: {
      access_token: 'demo-token',
      token_type: 'bearer',
      expires_in: 900,
      user: guestProfile,
      event_id: 'event-1',
      role: 'helper',
      expires_at: guestProfile.sandbox_expires_at,
    },
  }
}

/** A promise this test settles by hand, to hold a request open. */
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

beforeEach(() => {
  vi.clearAllMocks()
  // Real jsdom storage, shared by every case in the file — the tour's autostart
  // flag would otherwise survive from one case into the next.
  sessionStorage.clear()
  holders.locale.value = 'en'
  holders.authStore = reactive({
    profile: null as UserProfile | null,
    selectedEventId: null as string | null,
    ensureProfile: vi.fn(async () => {
      holders.authStore.profile = guestProfile
      return guestProfile
    }),
    eventRole: vi.fn(() => null),
  })
  delete window.__APP_CONFIG__
  setActivePinia(createPinia())
})

describe('useSandboxStore', () => {
  describe('enabled', () => {
    it('offers the demo when the deploy said nothing about it', () => {
      expect(useSandboxStore().enabled).toBe(true)
    })

    it('hides the demo only for the literal "false"', () => {
      window.__APP_CONFIG__ = { SANDBOX_ENABLED: 'false' }

      expect(useSandboxStore().enabled).toBe(false)
    })

    it('reads a shell-shaped "FALSE " the same way', () => {
      window.__APP_CONFIG__ = { SANDBOX_ENABLED: ' FALSE ' }

      expect(useSandboxStore().enabled).toBe(false)
    })

    it('treats any other value as switched on rather than guessing', () => {
      window.__APP_CONFIG__ = { SANDBOX_ENABLED: 'yes' }

      expect(useSandboxStore().enabled).toBe(true)
    })
  })

  describe('reading the current demo', () => {
    it('reports no demo for an ordinary account', () => {
      holders.authStore.profile = { id: 'u1' } as UserProfile
      const store = useSandboxStore()

      expect(store.isSandbox).toBe(false)
      expect(store.role).toBeNull()
      expect(store.expiresAt).toBeNull()
    })

    it('reports the demo and its expiry once a guest is signed in', () => {
      holders.authStore.profile = guestProfile
      const store = useSandboxStore()

      expect(store.isSandbox).toBe(true)
      expect(store.expiresAt).toBe('2026-08-24T12:00:00Z')
    })

    it('recovers the role from the event after a reload', () => {
      holders.authStore.profile = guestProfile
      holders.authStore.selectedEventId = 'event-1'
      holders.authStore.eventRole.mockReturnValue('owner')

      expect(useSandboxStore().role).toBe('manager')

      holders.authStore.eventRole.mockReturnValue('member')
      setActivePinia(createPinia())

      expect(useSandboxStore().role).toBe('helper')
    })

    it('has no role to report while the membership is still unknown', () => {
      holders.authStore.profile = guestProfile
      holders.authStore.eventRole.mockReturnValue(null)

      expect(useSandboxStore().role).toBeNull()
    })
  })

  describe('start', () => {
    it('mints a demo, installs the session and opens the dashboard', async () => {
      holders.post.mockResolvedValue(sandboxResponse())
      const store = useSandboxStore()

      await expect(store.start('manager')).resolves.toBe(true)

      expect(holders.post).toHaveBeenCalledWith(
        expect.objectContaining({
          url: '/auth/sandbox',
          body: { role: 'manager', language: 'en' },
          withCredentials: true,
        }),
      )
      expect(holders.setSession).toHaveBeenCalledWith(sandboxResponse().data)
      expect(holders.authStore.ensureProfile).toHaveBeenCalled()
      expect(holders.router.push).toHaveBeenCalledWith({ name: 'home' })
      expect(store.starting).toBe(false)
    })

    it('seeds the demo in the language the visitor is reading', async () => {
      holders.locale.value = 'de'
      holders.post.mockResolvedValue(sandboxResponse())

      await useSandboxStore().start('helper')

      expect(holders.post).toHaveBeenCalledWith(
        expect.objectContaining({ body: { role: 'helper', language: 'de' } }),
      )
    })

    it('drops the previous profile so the guest is not shown the old account', async () => {
      // Somebody who was already signed in: `ensureProfile()` short-circuits on
      // a profile that is already there, so the real one has to go first.
      holders.authStore.profile = { id: 'real-user' } as UserProfile
      holders.post.mockResolvedValue(sandboxResponse())
      const seen: (string | null)[] = []
      holders.authStore.ensureProfile.mockImplementation(async () => {
        seen.push(holders.authStore.profile?.id ?? null)
        holders.authStore.profile = guestProfile
        return guestProfile
      })

      await useSandboxStore().start('helper')

      expect(seen).toEqual([null])
      expect(holders.authStore.profile).toEqual(guestProfile)
    })

    it('remembers the role that was asked for', async () => {
      holders.post.mockResolvedValue(sandboxResponse())
      const store = useSandboxStore()

      await store.start('manager')

      // No call to `eventRole` needed: the store still knows what was clicked.
      expect(store.role).toBe('manager')
      expect(holders.authStore.eventRole).not.toHaveBeenCalled()
    })

    it('lets the tour introduce itself again in a tab that has already had one', async () => {
      // The second demo of a sitting: somebody who tried the helper side and
      // came back for the manager one, or whose first demo expired under them.
      // The autostart flag is per tab, so without this the whole point of the
      // second demo — seeing the *other* half of the product explained — is
      // silently withheld, with nothing on screen to say why.
      markAutoStarted()
      holders.post.mockResolvedValue(sandboxResponse())

      await useSandboxStore().start('manager')

      expect(hasAutoStarted()).toBe(false)
    })

    it('takes the tour from the previous demo off the screen', async () => {
      // Re-arming the flag is only half of it. Nothing here reloads the page,
      // and the tour keeps its place in `sessionStorage`, so a helper tour left
      // running two clicks ago would still be mid-sentence over the organiser
      // demo that replaced it — and `tour/install.ts` would decline to offer a
      // new one, because one is already running.
      const stopped = vi.fn()
      window.addEventListener(TOUR_STOP_EVENT, stopped)
      holders.post.mockResolvedValue(sandboxResponse())

      await useSandboxStore().start('manager')

      expect(stopped).toHaveBeenCalledOnce()
      window.removeEventListener(TOUR_STOP_EVENT, stopped)
    })

    it('leaves the flag alone when the demo was refused', async () => {
      // Nothing started, so this sitting's tour has still had its turn: a
      // failed request must not re-arm a tour over the demo already running.
      markAutoStarted()
      holders.post.mockRejectedValue(new Error('all demo slots taken'))

      await useSandboxStore().start('helper')

      expect(hasAutoStarted()).toBe(true)
    })

    it('surfaces a refusal and stays where it is', async () => {
      const failure = new Error('all demo slots taken')
      holders.post.mockRejectedValue(failure)
      const store = useSandboxStore()

      await expect(store.start('helper')).resolves.toBe(false)

      expect(holders.toastApiError).toHaveBeenCalledWith(failure)
      expect(holders.setSession).not.toHaveBeenCalled()
      expect(holders.router.push).not.toHaveBeenCalled()
      expect(store.starting).toBe(false)
    })

    it('ignores a second press while the first is still in flight', async () => {
      const pending = deferred<unknown>()
      holders.post.mockReturnValue(pending.promise)
      const store = useSandboxStore()

      const first = store.start('helper')
      expect(store.starting).toBe(true)
      await expect(store.start('manager')).resolves.toBe(false)

      pending.resolve(sandboxResponse())
      await expect(first).resolves.toBe(true)
      expect(holders.post).toHaveBeenCalledTimes(1)
    })
  })

  describe('exit', () => {
    it('deletes the demo, forgets the session and returns to the landing page', async () => {
      holders.del.mockResolvedValue(undefined)
      holders.authStore.profile = guestProfile
      const store = useSandboxStore()

      await store.exit()

      expect(holders.del).toHaveBeenCalledWith({ url: '/auth/sandbox' })
      // `deliberate` — this is not an expiry, so no breadcrumb for the landing
      // page to pick up and explain.
      expect(holders.clear).toHaveBeenCalledWith({ deliberate: true })
      expect(holders.authStore.profile).toBeNull()
      expect(holders.router.push).toHaveBeenCalledWith({ name: 'landing' })
      expect(store.exiting).toBe(false)
    })

    it('signs out locally even when the demo is already gone server-side', async () => {
      const failure = new Error('404')
      holders.del.mockRejectedValue(failure)
      holders.authStore.profile = guestProfile

      await useSandboxStore().exit()

      expect(holders.toastApiError).toHaveBeenCalledWith(failure)
      expect(holders.clear).toHaveBeenCalledWith({ deliberate: true })
      expect(holders.router.push).toHaveBeenCalledWith({ name: 'landing' })
    })

    it('ignores a second press while the first is still in flight', async () => {
      const pending = deferred<unknown>()
      holders.del.mockReturnValue(pending.promise)
      const store = useSandboxStore()

      const first = store.exit()
      expect(store.exiting).toBe(true)
      await store.exit()

      pending.resolve(undefined)
      await first
      expect(holders.del).toHaveBeenCalledTimes(1)
    })

    it('forgets the role it was started with', async () => {
      holders.post.mockResolvedValue(sandboxResponse())
      holders.del.mockResolvedValue(undefined)
      const store = useSandboxStore()
      await store.start('manager')

      holders.authStore.profile = null
      await store.exit()

      expect(store.role).toBeNull()
    })
  })
})
