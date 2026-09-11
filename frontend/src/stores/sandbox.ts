import { computed, ref } from 'vue'

import { defineStore } from 'pinia'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

import { useAppConfig } from '@/composables/useAppConfig'
import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import { client } from '@/client/client.gen'
import type { SandboxSessionResponse } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { authSession } from '@/lib/auth-session'
import i18n from '@/locales/i18n'
import { clearAutoStarted } from '@/tour/autostart'
import { endTour } from '@/tour/offer'

/**
 * The throwaway demo session.
 *
 * A visitor who has never signed up can press one button and land inside a real
 * event with real shifts, bookings and teammates. What the backend hands back is
 * not a special rendering mode — it is an ordinary session belonging to a guest
 * account that deletes itself an hour later, so everything downstream (the
 * router, the API client, the sidebar) treats the demo as a perfectly normal
 * sign-in and needs to know nothing about it.
 */

/** Which side of the app the demo opens on. */
export type SandboxRole = 'helper' | 'manager'

export const useSandboxStore = defineStore('sandbox', () => {
  const authStore = useAuthStore()
  const { delete: del } = useAuthenticatedClient()
  const router = useRouter()

  const starting = ref(false)
  const exiting = ref(false)
  /**
   * The role `start()` was asked for.
   *
   * Null after a reload — nothing in the browser remembers which button was
   * pressed — which is why `role` below can also read it back off the event.
   */
  const startedRole = ref<SandboxRole | null>(null)

  /**
   * Whether the demo is on offer at all.
   *
   * `SANDBOX_ENABLED` arrives from `config.js` as a *string*, so the test is
   * against the literal `'false'` and nothing else: a deploy whose `config.js`
   * predates the flag answers `undefined`, falls through to the `'true'`
   * default, and keeps the button. Turning the demo off is therefore an
   * explicit act in both halves — this only hides the entry points, the
   * backend's own `SANDBOX_ENABLED` is what actually refuses (404).
   */
  const enabled = computed(
    // `String(…)` because `config.js` is hand-editable in development and a
    // real boolean `false` there should mean what it looks like, not throw on
    // `.trim()`.
    () => String(useAppConfig().SANDBOX_ENABLED).trim().toLowerCase() !== 'false',
  )

  /** True while a demo account is the one signed in. */
  const isSandbox = computed(() => authStore.profile?.is_sandbox === true)

  /** When the demo is swept away, as an ISO timestamp, or null outside a demo. */
  const expiresAt = computed(() => authStore.profile?.sandbox_expires_at ?? null)

  const role = computed<SandboxRole | null>(() => {
    if (!isSandbox.value) return null
    if (startedRole.value) return startedRole.value
    // After a reload the store is new but the event is not: the manager owns
    // the demo event, the helper is an ordinary member of it. So the role is
    // recoverable without persisting anything of our own.
    const eventRole = authStore.eventRole(authStore.selectedEventId)
    if (!eventRole) return null
    return eventRole === 'member' ? 'helper' : 'manager'
  })

  /** The language the seeded event should read in — whatever the page is in now. */
  function currentLanguage(): 'en' | 'de' {
    return i18n.global.locale.value === 'de' ? 'de' : 'en'
  }

  /**
   * Mint a demo and walk into it.
   *
   * Resolves `true` when the visitor is now inside the demo, `false` when the
   * request was refused — the caller uses that to decide whether to close its
   * dialog. The error itself is already on screen by then.
   */
  async function start(role: SandboxRole): Promise<boolean> {
    if (starting.value) return false
    starting.value = true
    try {
      // The *unauthenticated* client, deliberately. There is no token to send
      // yet, and if a real account happens to be signed in, its bearer must not
      // ride along on the request that replaces it. `withCredentials` is what
      // lets the refresh cookie come back — the same door `/auth/login` uses.
      const response = await client.post<{ data: SandboxSessionResponse }, unknown, true>({
        url: '/auth/sandbox',
        body: { role, language: currentLanguage() },
        throwOnError: true,
        withCredentials: true,
      })

      // Installed exactly the way a password login is. Note what is *not* done
      // here: `authSession.bootstrap` is left alone. A real refresh cookie came
      // back with this response, so the ordinary boot-time refresh is what
      // keeps the demo alive across an F5 — stubbing it out, the way the E2E
      // bypass does, would end the demo at the first reload.
      authSession.setSession(response.data)

      // A second demo in the same tab is a second first impression, so the tour
      // is allowed to introduce itself again. Here rather than in `exit()`,
      // which an *expired* demo never reaches — that one ends at the 401 in
      // `requestRefresh` and is restarted from the landing page's dialog — and
      // `start()` is in any case the exact moment the fact becomes true. The
      // flag lives in `tour/autostart.ts` rather than in `tour/install.ts`
      // precisely so this line does not drag driver.js into the landing page's
      // bundle.
      clearAutoStarted()
      // …and the tour from the demo just abandoned goes with it. The store
      // keeps its place in `sessionStorage`, and nothing here reloads the page,
      // so without this a second demo opened in the same tab inherits the first
      // one's popover — an organiser being told, mid-sentence, what they are
      // already down for as a volunteer.
      endTour()

      // `ensureProfile()` short-circuits on whatever profile is already loaded,
      // which for somebody who was signed in a moment ago is still their real
      // account. Drop it so the guest's own profile — and with it the preset
      // selected event — is actually fetched.
      authStore.profile = null
      startedRole.value = role
      await authStore.ensureProfile()

      // Straight to the dashboard: the guest already has a selected event, so
      // the picker would only be a frame between them and the thing they asked
      // to see.
      await router.push({ name: 'home' })
      return true
    } catch (error) {
      toastApiError(error)
      return false
    } finally {
      starting.value = false
    }
  }

  /**
   * Destroy the demo and leave.
   *
   * The local teardown runs whether or not the server call succeeded: the guest
   * may already have been swept away, and that is no reason to leave somebody
   * looking signed in to an account that no longer exists.
   */
  async function exit(): Promise<void> {
    if (exiting.value) return
    exiting.value = true
    try {
      await del({ url: '/auth/sandbox' })
    } catch (error) {
      toastApiError(error)
    }

    startedRole.value = null
    authStore.profile = null
    // `deliberate`, so no "your demo ended" breadcrumb is left behind. Somebody
    // who just pressed *Exit demo* does not need the landing page to break the
    // news to them.
    authSession.clear({ deliberate: true })
    exiting.value = false
    await router.push({ name: 'landing' })
  }

  return { enabled, isSandbox, role, expiresAt, starting, exiting, start, exit }
})
