import { authGuard as _authGuard } from '@auth0/auth0-vue'
import { createRouter, createWebHistory } from 'vue-router'

// In E2E bypass mode, skip Auth0's authGuard entirely since the fake plugin
// doesn't set the module-level client ref that authGuard reads.
const authGuard =
  import.meta.env.VITE_E2E_AUTH_BYPASS === 'true' && document.cookie.includes('e2e_bypass=1')
    ? () => true
    : _authGuard

import { useAuthStore } from '@/stores/auth'
import type { BreadcrumbItem } from '@/stores/breadcrumb'

// Extend route meta to include breadcrumbs and layout
declare module 'vue-router' {
  interface RouteMeta {
    breadcrumbs?: BreadcrumbItem[]
    layout?: 'preauth' | 'postauth' | 'minimal'
    requiresRole?: string | string[]
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
        },
        {
          path: 'about',
          name: 'about',
          component: () => import('@/views/preauth/AboutView.vue'),
        },
        {
          path: 'how-it-works',
          name: 'how-it-works',
          component: () => import('@/views/preauth/HowItWorksView.vue'),
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
          path: 'event-groups',
          name: 'event-groups',
          component: () => import('@/views/event-groups/EventGroupsView.vue'),
          meta: {
            breadcrumbs: [{ title: 'Event Groups', titleKey: 'duties.eventGroups.title' }],
          },
        },
        {
          path: 'event-groups/:groupId',
          name: 'event-group-detail',
          component: () => import('@/views/event-groups/EventGroupDetailView.vue'),
          meta: {
            breadcrumbs: [
              {
                title: 'Event Groups',
                titleKey: 'duties.eventGroups.title',
                to: { name: 'event-groups' },
              },
              { title: 'Event Group Details', titleKey: 'duties.eventGroups.detail.title' },
            ],
          },
        },
        {
          path: 'events',
          name: 'events',
          component: () => import('@/views/events/EventsView.vue'),
          meta: {
            breadcrumbs: [{ title: 'Events', titleKey: 'duties.events.title' }],
          },
        },
        {
          path: 'events/create',
          name: 'event-create',
          component: () => import('@/views/events/EventCreateView.vue'),
          meta: {
            requiresRole: 'admin',
            breadcrumbs: [
              { title: 'Events', titleKey: 'duties.events.title', to: { name: 'events' } },
              { title: 'Create Event', titleKey: 'duties.events.createView.title' },
            ],
          },
        },
        {
          path: 'events/:eventId/edit',
          name: 'event-edit',
          component: () => import('@/views/events/EventEditView.vue'),
          meta: {
            requiresRole: 'admin',
            breadcrumbs: [
              { title: 'Events', titleKey: 'duties.events.title', to: { name: 'events' } },
              { title: 'Edit Event', titleKey: 'duties.events.editView.title' },
            ],
          },
        },
        {
          path: 'events/:eventId/add-slots',
          name: 'event-add-slots',
          component: () => import('@/views/events/EventAddSlotsView.vue'),
          meta: {
            requiresRole: 'admin',
            breadcrumbs: [
              { title: 'Events', titleKey: 'duties.events.title', to: { name: 'events' } },
              { title: 'Add Slots', titleKey: 'duties.events.addSlotsView.title' },
            ],
          },
        },
        {
          path: 'events/:eventId',
          name: 'event-detail',
          component: () => import('@/views/events/EventDetailView.vue'),
          meta: {
            breadcrumbs: [
              { title: 'Events', titleKey: 'duties.events.title', to: { name: 'events' } },
              { title: 'Event Details', titleKey: 'duties.events.detail.title' },
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
          path: 'admin/reporting',
          name: 'admin-reporting',
          component: () => import('@/views/admin/ReportingView.vue'),
          meta: {
            requiresRole: 'admin',
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
          path: 'events/:eventId',
          name: 'print-event',
          component: () => import('@/views/print/PrintEventView.vue'),
        },
        {
          path: 'event-groups/:groupId',
          name: 'print-event-group',
          component: () => import('@/views/print/PrintEventGroupView.vue'),
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
          path: 'pending-approval',
          name: 'pending-approval',
          component: () => import('@/views/PendingApprovalView.vue'),
        },
      ],
    },

    // Catch-all route - redirect to 404 in no layout
    {
      path: '/:pathMatch(.*)*',
      redirect: { name: 'not-found' },
    },
  ],
})

const normalizeRoles = (roles: string | string[]) => (Array.isArray(roles) ? roles : [roles])

router.beforeEach(async (to) => {
  const authStore = useAuthStore()

  console.log('Auth0 isLoading:', authStore.auth0.isLoading)

  // Wait for Auth0 to finish loading before checking authentication
  while (authStore.auth0.isLoading) {
    await new Promise((resolve) => setTimeout(resolve, 100))
  }

  console.log('Checking access for route:', to.name)
  // print auth store authenticated status and roles
  console.log('User is authenticated:', authStore.isAuthenticated)
  console.log('User roles:', authStore.roles)

  if (authStore.isAuthenticated) {
    try {
      await authStore.ensureProfile()
    } catch (error) {
      console.error('Failed to load user profile for role check:', error)
      if (to.meta.requiresRole) {
        return { name: 'home' }
      }
    }

    // Redirect inactive users to pending approval page
    if (!authStore.isActive && to.name !== 'pending-approval') {
      return { name: 'pending-approval' }
    }
    // Don't let active users visit the pending page
    if (authStore.isActive && to.name === 'pending-approval') {
      return { name: 'home' }
    }
  }

  if (!to.meta.requiresRole) return true
  if (!authStore.isAuthenticated) return true

  const requiredRoles = normalizeRoles(to.meta.requiresRole)
  const hasAllRoles = requiredRoles.every((role) => authStore.roles.includes(role))
  if (!hasAllRoles) {
    return { name: 'home' }
  }

  return true
})

export default router
