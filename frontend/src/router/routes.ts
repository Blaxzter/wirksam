import type { NavigationGuard, RouteRecordRaw } from 'vue-router'

import type { BreadcrumbItem } from '@/stores/breadcrumb'

import { DEFAULT_PUBLIC_LOCALE, PUBLIC_LOCALES } from '@/lib/seo'

const PREFIXED_LOCALES = PUBLIC_LOCALES.filter((locale) => locale !== DEFAULT_PUBLIC_LOCALE)

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

/**
 * The route table, kept apart from `index.ts` so it can be built without a
 * browser. The build-time prerender (`scripts/prerender.mjs`) renders the public
 * pages from these same records, with a guard that lets everything through —
 * which is why the guard is a parameter instead of an import.
 */
export function createRoutes(authGuard: NavigationGuard): RouteRecordRaw[] {
  return [
    // Layout wrappers as parent routes
    // The public pages exist once per language: bare for English, under `/de`
    // for German, so a crawler can index both and each gets its own URL. Named
    // links inherit the param, so a visitor who arrived in German stays there.
    // `lib/page-head.ts` sets the app locale from it.
    {
      path: `/:locale(${PREFIXED_LOCALES.join('|')})?`,
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
        // Same screen, other reason: the account is waiting in (or was turned
        // away from) the approval queue. The view reads which from the store.
        {
          path: 'account-pending',
          name: 'account-pending',
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
  ]
}
