import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

import { isSwitchOn, useAppConfig } from '@/composables/useAppConfig'
import { authGuard as sessionAuthGuard } from '@/composables/useAuth'

import { SANDBOX_ENDED_KEY, authSession } from '@/lib/auth-session'
import { publicPageFor } from '@/lib/seo'

import { createRoutes } from './routes'

/**
 * E2E signs in by installing a session directly rather than by logging in, so
 * both halves of the real flow have to stand aside here: the guard, and the
 * bootstrap below. The bootstrap is the dangerous one — its `POST /auth/refresh`
 * would answer 401 for a browser that holds no refresh cookie, and a 401 clears
 * the session, including the one the bypass just installed.
 */
const isE2eBypass =
  import.meta.env.VITE_E2E_AUTH_BYPASS === 'true' && document.cookie.includes('e2e_bypass=1')

const authGuard = isE2eBypass ? () => true : sessionAuthGuard

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: createRoutes(authGuard),

  /**
   * The landing page is one long document with linkable sections, so a hash
   * has to actually scroll somewhere. `scroll-mt-*` on each section handles
   * the sticky header offset, and `savedPosition` keeps the back button
   * returning to where the visitor was.
   */
  scrollBehavior(to, _from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.hash) return { el: to.hash, behavior: 'smooth' }
    return { top: 0 }
  },
})

const landingEnabled = () => isSwitchOn(useAppConfig().LANDING_ENABLED)

const normalizeRoles = (roles: string | string[]) => (Array.isArray(roles) ? roles : [roles])

// Routes that bypass the "must have a selected event" guard
const SELECTED_EVENT_EXEMPT_ROUTES = new Set<string>([
  'select-event',
  'my-events',
  // Creating an event is the way out of having none, so it cannot sit behind
  // the gate that demands one.
  'event-create',
  // The event worth cloning is usually the one that has just finished, and an
  // expired selection is exactly what this guard bounces. Gating the clone
  // wizard on it would shut the door on its main use.
  'event-clone',
  'event-settings',
  'admin-users',
  'admin-demo-data',
  'settings',
  'notification-preferences',
  // An invite link has to work before you belong to anything.
  'invite-accept',
  'account-suspended',
  'account-pending',
  'changelog',
  'preauth-changelog',
  // The auth screens, for the same reason: an account that was created a second
  // ago has no selected event, and bouncing a verification link into the event
  // picker would swallow the token it was carrying.
  'login',
  'register',
  'forgot-password',
  'reset-password',
  'verify-email',
])

/**
 * Auth screens that make no sense to somebody who is already signed in.
 *
 * `reset-password` and `verify-email` are deliberately absent: both carry a
 * one-shot token that has to be redeemable in whichever browser the mail was
 * opened in, signed in or not.
 */
const SIGNED_IN_REDIRECT_ROUTES = new Set<string>(['login', 'register'])

/**
 * Whether this browser is carrying "your demo just ended".
 *
 * Peeked at, never consumed — `SandboxExpiredDialog` on the landing page is
 * what removes it, and removing it here would mean the explanation is thrown
 * away by the very redirect that exists to deliver it.
 */
function sandboxJustEnded(): boolean {
  try {
    return sessionStorage.getItem(SANDBOX_ENDED_KEY) !== null
  } catch {
    // A browser that blocks site data. Nothing to route on.
    return false
  }
}

router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  const routeName = typeof to.name === 'string' ? to.name : ''

  // Await the one-shot session restore instead of polling a loading flag. The
  // first navigation routinely beats the app's own `bootstrap()` to the punch,
  // and deciding this guard against a session that has not been restored yet
  // signs everybody out on every reload.
  if (!isE2eBypass) await authSession.bootstrap()

  // A deployment without the landing page (`LANDING_ENABLED=false`) sends `/`,
  // and the content pages that go with it (`requires` in lib/seo.ts), where the
  // visitor would go from there anyway: in, or to the sign-in screen.
  if (publicPageFor(routeName)?.requires === 'LANDING_ENABLED' && !landingEnabled()) {
    return authStore.isAuthenticated ? { name: 'home' } : { name: 'login' }
  }

  if (authStore.isAuthenticated) {
    try {
      await authStore.ensureProfile()
    } catch (error) {
      console.error('Failed to load user profile for role check:', error)
      if (to.meta.requiresRole) {
        return { name: 'home' }
      }
    }

    // An account that may sign in but not use the app gets told why rather
    // than left on a page where every request comes back 403: suspended by a
    // moderator, or waiting in (or rejected from) the approval queue.
    const blockedRoute = !authStore.isActive
      ? 'account-suspended'
      : !authStore.isApproved
        ? 'account-pending'
        : null
    if (blockedRoute && routeName !== blockedRoute) {
      return { name: blockedRoute }
    }
    if (!blockedRoute && (routeName === 'account-suspended' || routeName === 'account-pending')) {
      return { name: 'home' }
    }

    // A bookmarked /login or a stale tab should not present a sign-in form to
    // somebody who is already signed in.
    if (SIGNED_IN_REDIRECT_ROUTES.has(routeName)) {
      return { name: 'home' }
    }

    // A demo guest belongs to exactly one event and the picker is the door out
    // of it — switching away, or asking to join something else, would strand
    // them in an app with nothing left to show. Their event is already
    // selected, so the picker has nothing to offer them either way.
    if (authStore.profile?.is_sandbox && routeName === 'select-event') {
      return { name: 'home' }
    }

    // Selected-event gate: force users without a valid selection into the picker
    const isExempt = SELECTED_EVENT_EXEMPT_ROUTES.has(routeName)
    if (authStore.isActive && !isExempt) {
      if (!authStore.selectedEventId) {
        return { name: 'select-event', query: { mode: 'onboarding' } }
      }
      if (authStore.selectedEvent?.is_expired) {
        return { name: 'select-event', query: { mode: 'expired' } }
      }
    }
  }

  if (!authStore.isAuthenticated) {
    // The sign-in screen is the wrong answer for a demo guest whose session was
    // just swept away: they never had a password, so the form in front of them
    // is unusable. `authGuard` cannot know that — it sends every dead session
    // to `login` — so the redirect it starts is caught here on its way past and
    // sent to the landing page, which carries the explanation and the offer of
    // another demo.
    // Without a landing page there is nowhere better than the sign-in screen,
    // and sending it there would bounce straight back here.
    if (routeName === 'login' && sandboxJustEnded() && landingEnabled()) {
      return { name: 'landing' }
    }
    return true
  }

  // Pages that only make sense to someone who runs at least one event. The
  // per-event decision still belongs to the view and the API; this just keeps
  // a participant from landing on an empty management screen.
  if (to.meta.requiresEventManager && !authStore.isManager) {
    return { name: 'home' }
  }

  if (!to.meta.requiresRole) return true

  const requiredRoles = normalizeRoles(to.meta.requiresRole)
  if (!requiredRoles.some((role) => authStore.roles.includes(role))) {
    return { name: 'home' }
  }

  return true
})

export default router
