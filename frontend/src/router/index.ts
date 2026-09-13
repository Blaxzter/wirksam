import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import type { BreadcrumbItem } from '@/stores/breadcrumb'

import { authGuard as sessionAuthGuard } from '@/composables/useAuth'

import { SANDBOX_ENDED_KEY, authSession } from '@/lib/auth-session'

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

// Extend route meta to include breadcrumbs and layout
declare module 'vue-router' {
  interface RouteMeta {
    breadcrumbs?: BreadcrumbItem[]
    layout?: 'preauth' | 'postauth' | 'minimal'
    /** Route renders its own full-bleed sections; the pre-auth shell skips its page container. */
    fullBleed?: boolean
    /** Platform-wide role. Only 'admin' (superadmin) is still meaningful. */
    requiresRole?: string | string[]
    /**
     * Requires owner/admin on *some* event. Per-event checks still happen in
     * the view and on the server — this only keeps the nav honest by hiding
     * pages a participant could never use.
     */
    requiresEventManager?: boolean
  }
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    // Layout wrappers as parent routes
    {
      path: '/',
      name: 'preauth-layout',
      component: () => import('@/layout/PreAuthLayout.vue'),
      children: [
        {
          path: '',
          name: 'landing',
          component: () => import('@/views/preauth/LandingView.vue'),
          meta: { fullBleed: true },
        },
        // The About and How-It-Works pages were folded into the landing page as
        // sections. Both paths were linked from outside the app, so they keep
        // working as redirects to the anchor that replaced them.
        {
          path: 'about',
          name: 'about',
          redirect: { name: 'landing', hash: '#about' },
        },
        {
          path: 'how-it-works',
          name: 'how-it-works',
          redirect: { name: 'landing', hash: '#how-it-works' },
        },
        {
          path: 'privacy',
          name: 'privacy',
          component: () => import('@/views/preauth/PrivacyView.vue'),
        },
        {
          path: 'terms',
          name: 'terms',
          component: () => import('@/views/preauth/TermsView.vue'),
        },
        {
          path: 'impressum',
          name: 'impressum',
          component: () => import('@/views/preauth/ImpressumView.vue'),
        },
        {
          path: 'changelog/:version?',
          name: 'preauth-changelog',
          component: () => import('@/views/ChangelogView.vue'),
        },
      ],
    },
    {
      path: '/app',
      name: 'postauth-layout',
      redirect: { name: 'home' },
      component: () => import('@/layout/PostAuthLayout.vue'),
      beforeEnter: authGuard,
      children: [
        {
          path: 'home',
          name: 'home',
          component: () => import('@/views/HomeView.vue'),
          meta: {
            breadcrumbs: [{ title: 'Home', titleKey: 'navigation.breadcrumbs.home' }],
          },
        },
        {
          path: 'availability',
          name: 'availability',
          component: () => import('@/views/events/AvailabilityView.vue'),
          meta: {
            breadcrumbs: [{ title: 'Availability', titleKey: 'duties.availability.title' }],
          },
        },
        {
          path: 'print',
          name: 'event-print',
          component: () => import('@/views/events/PrintView.vue'),
          meta: {
            breadcrumbs: [{ title: 'Print', titleKey: 'duties.events.detail.nav.print' }],
          },
        },
        {
          path: 'event-settings/:eventId?',
          name: 'event-settings',
          component: () => import('@/views/events/EventSettingsView.vue'),
          meta: {
            breadcrumbs: [{ title: 'Event Details', titleKey: 'duties.events.detail.title' }],
          },
        },
        {
          path: 'events',
          name: 'my-events',
          component: () => import('@/views/admin/AdminEventsView.vue'),
          meta: {
            requiresEventManager: true,
            breadcrumbs: [
              { title: 'Home', titleKey: 'navigation.breadcrumbs.home', to: { name: 'home' } },
              { title: 'My Events', titleKey: 'admin.events.title' },
            ],
          },
        },
        {
          // Deliberately not `requiresEventManager`: running your first event
          // is how you become a manager, and the picker offers this to a
          // brand-new account.
          path: 'events/create',
          name: 'event-create',
          component: () => import('@/views/events/EventCreateView.vue'),
          meta: {
            breadcrumbs: [
              { title: 'Home', titleKey: 'navigation.breadcrumbs.home', to: { name: 'home' } },
              { title: 'Create Event', titleKey: 'duties.events.createView.title' },
            ],
          },
        },
        {
          // Cloning last year's event is the point of this screen, and last
          // year's event is expired — see SELECTED_EVENT_EXEMPT_ROUTES.
          path: 'events/clone/:sourceId',
          name: 'event-clone',
          component: () => import('@/views/events/EventCloneView.vue'),
          meta: {
            requiresEventManager: true,
            breadcrumbs: [
              { title: 'Home', titleKey: 'navigation.breadcrumbs.home', to: { name: 'home' } },
              { title: 'My Events', titleKey: 'admin.events.title', to: { name: 'my-events' } },
              { title: 'Clone Event', titleKey: 'duties.events.clone.title' },
            ],
          },
        },
        {
          path: 'tasks',
          name: 'tasks',
          component: () => import('@/views/tasks/TasksView.vue'),
          meta: {
            breadcrumbs: [{ title: 'Tasks', titleKey: 'duties.tasks.title' }],
          },
        },
        {
          path: 'tasks/create',
          name: 'task-create',
          component: () => import('@/views/tasks/TaskCreateView.vue'),
          meta: {
            requiresEventManager: true,
            breadcrumbs: [
              { title: 'Tasks', titleKey: 'duties.tasks.title', to: { name: 'tasks' } },
              { title: 'Create Task', titleKey: 'duties.tasks.createView.title' },
            ],
          },
        },
        {
          path: 'tasks/:eventId/edit',
          name: 'task-edit',
          component: () => import('@/views/tasks/TaskEditView.vue'),
          meta: {
            requiresEventManager: true,
            breadcrumbs: [
              { title: 'Tasks', titleKey: 'duties.tasks.title', to: { name: 'tasks' } },
              { title: 'Edit Task', titleKey: 'duties.tasks.editView.title' },
            ],
          },
        },
        {
          path: 'tasks/:eventId/add-shifts',
          name: 'task-add-shifts',
          component: () => import('@/views/tasks/TaskAddShiftsView.vue'),
          meta: {
            requiresEventManager: true,
            breadcrumbs: [
              { title: 'Tasks', titleKey: 'duties.tasks.title', to: { name: 'tasks' } },
              { title: 'Add Shifts', titleKey: 'duties.tasks.addShiftsView.title' },
            ],
          },
        },
        {
          path: 'tasks/:eventId',
          name: 'task-detail',
          component: () => import('@/views/tasks/TaskDetailView.vue'),
          meta: {
            breadcrumbs: [
              { title: 'Tasks', titleKey: 'duties.tasks.title', to: { name: 'tasks' } },
              { title: 'Task Details', titleKey: 'duties.tasks.detail.title' },
            ],
          },
        },
        {
          path: 'bookings',
          name: 'my-bookings',
          component: () => import('@/views/bookings/MyBookingsView.vue'),
          meta: {
            breadcrumbs: [{ title: 'My Bookings', titleKey: 'duties.bookings.title' }],
          },
        },
        {
          path: 'bookings/:bookingId',
          name: 'booking-detail',
          component: () => import('@/views/bookings/BookingDetailView.vue'),
          meta: {
            breadcrumbs: [
              {
                title: 'My Bookings',
                titleKey: 'duties.bookings.title',
                to: { name: 'my-bookings' },
              },
              { title: 'Booking Details', titleKey: 'duties.bookings.detail.title' },
            ],
          },
        },
        {
          path: 'changelog/:version?',
          name: 'changelog',
          component: () => import('@/views/ChangelogView.vue'),
          meta: {
            routerViewKey: 'changelog',
            breadcrumbs: [
              { title: 'Home', titleKey: 'navigation.breadcrumbs.home', to: { name: 'home' } },
              { title: "What's New", titleKey: 'changelog.title' },
            ],
          },
        },
        {
          path: 'notifications',
          name: 'notifications',
          component: () => import('@/views/NotificationsView.vue'),
          meta: {
            breadcrumbs: [
              { title: 'Home', titleKey: 'navigation.breadcrumbs.home', to: { name: 'home' } },
              { title: 'Notifications', titleKey: 'notifications.title' },
            ],
          },
        },
        {
          path: 'settings/notification-preferences',
          name: 'notification-preferences',
          component: () => import('@/views/NotificationPreferencesView.vue'),
          meta: {
            breadcrumbs: [
              { title: 'Home', titleKey: 'navigation.breadcrumbs.home', to: { name: 'home' } },
              {
                title: 'Settings',
                titleKey: 'navigation.breadcrumbs.settings',
                to: { name: 'settings' },
              },
              { title: 'Notifications', titleKey: 'notifications.preferences.title' },
            ],
          },
        },
        {
          path: 'settings/:section?',
          name: 'settings',
          component: () => import('@/views/UserSettingsView.vue'),
          meta: {
            routerViewKey: 'settings',
            breadcrumbs: [
              { title: 'Home', titleKey: 'navigation.breadcrumbs.home', to: { name: 'home' } },
              { title: 'Settings', titleKey: 'navigation.breadcrumbs.settings' },
            ],
          },
        },
        {
          path: 'reporting',
          name: 'reporting',
          component: () => import('@/views/admin/ReportingView.vue'),
          meta: {
            requiresEventManager: true,
            breadcrumbs: [
              { title: 'Home', titleKey: 'navigation.breadcrumbs.home', to: { name: 'home' } },
              { title: 'Reports', titleKey: 'admin.reporting.title' },
            ],
          },
        },
        {
          path: 'admin/demo-data',
          name: 'admin-demo-data',
          component: () => import('@/views/admin/DemoDataView.vue'),
          meta: {
            requiresRole: 'admin',
            breadcrumbs: [
              { title: 'Home', titleKey: 'navigation.breadcrumbs.home', to: { name: 'home' } },
              { title: 'Demo Data', titleKey: 'admin.demoData.title' },
            ],
          },
        },
        {
          path: 'admin/users',
          name: 'admin-users',
          component: () => import('@/views/admin/UsersView.vue'),
          meta: {
            requiresRole: 'admin',
            breadcrumbs: [
              { title: 'Home', titleKey: 'navigation.breadcrumbs.home', to: { name: 'home' } },
              { title: 'User Management', titleKey: 'admin.users.title' },
            ],
          },
        },
      ],
    },
    {
      path: '/print',
      name: 'print-layout',
      component: () => import('@/layout/PrintLayout.vue'),
      beforeEnter: authGuard,
      children: [
        {
          path: 'tasks/:eventId',
          name: 'print-task',
          component: () => import('@/views/print/PrintTaskView.vue'),
        },
        {
          path: 'events/:eventId',
          name: 'print-event',
          component: () => import('@/views/print/PrintEventView.vue'),
        },
      ],
    },
    {
      path: '/',
      name: 'no-layout',
      redirect: { name: 'landing' },
      component: () => import('@/layout/NoLayout.vue'),
      children: [
        {
          path: '404',
          name: 'not-found',
          component: () => import('@/views/NotFoundView.vue'),
        },
        {
          path: 'invite/:token',
          name: 'invite-accept',
          component: () => import('@/views/events/InviteAcceptView.vue'),
        },
        {
          path: 'account-suspended',
          name: 'account-suspended',
          component: () => import('@/views/AccountSuspendedView.vue'),
        },
      ],
    },
    // The five public auth screens. They have their own frame rather than
    // sitting in `NoLayout`: they paint a full-bleed split screen, and
    // `NoLayout`'s centred container would inset it and cap its width. They
    // still carry no navigation — a page asking for a password should not also
    // offer a bar full of places to go instead, and the only links each of them
    // has belong to the flow it is part of. Left unnamed on purpose: a named
    // parent with children and no default child warns at runtime.
    {
      path: '/',
      component: () => import('@/layout/AuthLayout.vue'),
      children: [
        {
          path: 'login',
          name: 'login',
          component: () => import('@/views/auth/LoginView.vue'),
        },
        {
          path: 'register',
          name: 'register',
          component: () => import('@/views/auth/RegisterView.vue'),
        },
        {
          path: 'forgot-password',
          name: 'forgot-password',
          component: () => import('@/views/auth/ForgotPasswordView.vue'),
        },
        // Both of these carry their secret in `?token=`, matching the links the
        // backend mails out. A route param would put the token in the URL a
        // breadcrumb or a referrer header could carry off.
        {
          path: 'reset-password',
          name: 'reset-password',
          component: () => import('@/views/auth/ResetPasswordView.vue'),
        },
        {
          path: 'verify-email',
          name: 'verify-email',
          component: () => import('@/views/auth/VerifyEmailView.vue'),
        },
      ],
    },
    {
      path: '/app/select-event',
      name: 'select-event',
      component: () => import('@/views/events/SelectEventView.vue'),
      beforeEnter: authGuard,
    },

    // Catch-all route - redirect to 404 in no layout
    {
      path: '/:pathMatch(.*)*',
      redirect: { name: 'not-found' },
    },
  ],

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

  if (authStore.isAuthenticated) {
    try {
      await authStore.ensureProfile()
    } catch (error) {
      console.error('Failed to load user profile for role check:', error)
      if (to.meta.requiresRole) {
        return { name: 'home' }
      }
    }

    // Suspension is still a moderation tool even though the approval queue is
    // gone, so a suspended account gets told rather than left on a page where
    // every request comes back 403.
    if (!authStore.isActive && to.name !== 'account-suspended') {
      return { name: 'account-suspended' }
    }
    if (authStore.isActive && to.name === 'account-suspended') {
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
    if (routeName === 'login' && sandboxJustEnded()) {
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
