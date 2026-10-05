import { computed, markRaw, ref, watch } from 'vue'

import { defineStore } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuth } from '@/composables/useAuth'
import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { type Palette, usePalette } from '@/composables/usePalette'

import ActionToast from '@/components/ui/sonner/ActionToast.vue'

import type { EventRead, UserProfile } from '@/client/types.gen'
import type { AuthUser } from '@/lib/auth-session'
import type { EventRole } from '@/lib/event-roles'
import i18n from '@/locales/i18n'
import { whenTourIsOver } from '@/tour/quiet'

// `User` is the name the components that render the signed-in identity already
// import; it now points at our own shape instead of the identity provider's.
export type { AuthUser, AuthUser as User }

export const useAuthStore = defineStore('auth', () => {
  const session = useAuth()
  const { get, put } = useAuthenticatedClient()
  const { t } = useI18n()
  const router = useRouter()
  const loading = ref(false)
  const profileLoading = ref(false)
  const pendingJoinRequestCount = ref(0)
  let joinRequestToastShown = false

  const isAuthenticated = computed(() => session.isAuthenticated.value)
  const user = computed(() => session.user.value)
  const profile = ref<UserProfile | null>(null)
  const roles = computed(() => profile.value?.roles ?? [])
  /** Platform superadmin — the only global role left. */
  const isAdmin = computed(() => profile.value?.is_admin ?? false)
  /** This user's role in each event they belong to, keyed by event id. */
  const eventRoles = computed<Record<string, EventRole>>(
    () => (profile.value?.event_roles ?? {}) as Record<string, EventRole>,
  )
  const myEventIds = computed(() => Object.keys(eventRoles.value))
  /** Events this user owns or administers — where they see management UI. */
  const managedEventIds = computed(() =>
    myEventIds.value.filter((id) => eventRoles.value[id] !== 'member'),
  )
  const isEventManager = computed(() => managedEventIds.value.length > 0)
  const isManager = computed(() => isAdmin.value || isEventManager.value)
  const isActive = computed(() => profile.value?.is_active ?? true)
  /**
   * Where the account stands in the registration queue. Only ever not
   * "approved" on a deployment running `REGISTRATION_MODE=approval`.
   */
  const approvalStatus = computed(() => profile.value?.approval_status ?? 'approved')
  const isApproved = computed(() => approvalStatus.value === 'approved')
  const selectedEventId = computed(() => profile.value?.selected_event_id ?? null)
  const selectedEvent = ref<EventRead | null>(null)

  /** This user's role in one event, or null if they are not in it. */
  function eventRole(eventId: string | null | undefined): EventRole | null {
    if (isAdmin.value) return 'owner'
    if (!eventId) return null
    return eventRoles.value[eventId] ?? null
  }

  /** Whether the user may manage the event (owner or admin). */
  function canManageEvent(eventId: string | null | undefined): boolean {
    const role = eventRole(eventId)
    return role === 'owner' || role === 'admin'
  }

  /** Whether the user owns the event — required to delete it or hand it on. */
  function isEventOwner(eventId: string | null | undefined): boolean {
    return eventRole(eventId) === 'owner'
  }

  /** Whether the user belongs to the event at all. */
  function isEventMember(eventId: string | null | undefined): boolean {
    return eventRole(eventId) !== null
  }

  let profilePromise: Promise<UserProfile | null> | null = null

  /** Revoke the session server-side, drop it locally and leave for the landing page. */
  const logout = async () => {
    profile.value = null
    await session.logout()
  }

  const getAccessToken = async () => {
    try {
      return await session.getAccessTokenSilently()
    } catch (error) {
      console.error('Error getting access token:', error)
      throw error
    }
  }

  const updateUser = (userData: Partial<AuthUser>) => {
    if (!isAuthenticated.value || !session.user.value) return

    session.user.value = {
      ...session.user.value,
      ...userData,
    }
  }

  const loadSelectedEvent = async (eventId: string | null) => {
    if (!eventId) {
      selectedEvent.value = null
      return
    }
    try {
      const res = await get<{ data: EventRead }>({ url: `/events/${eventId}` })
      selectedEvent.value = res.data
    } catch {
      selectedEvent.value = null
    }
  }

  const setSelectedEvent = async (id: string | null) => {
    const response = await put<{ data: UserProfile }>({
      url: '/users/me/selected-event',
      body: { selected_event_id: id },
    })
    profile.value = response.data
    await loadSelectedEvent(response.data.selected_event_id ?? null)
    return response.data
  }

  const loadProfile = async () => {
    if (!isAuthenticated.value) return null
    if (profilePromise) return await profilePromise

    profileLoading.value = true
    profilePromise = (async () => {
      // A plain read. Accounts are created by registering, not by turning up
      // with a token from somewhere else, so there is nothing to upsert here.
      const response = await get<{ data: UserProfile }>({ url: '/users/me' })
      profile.value = response.data

      // The session carries an identity only when it was minted by a sign-in.
      // After a reload it is restored from a cookie, which says who you are to
      // the server and nothing at all to the browser — so this is where the
      // shell (name, avatar, verification badge) gets one.
      session.user.value = response.data

      // Apply server-side language preference
      if (response.data.preferred_language) {
        i18n.global.locale.value = response.data.preferred_language as 'en' | 'de'
        localStorage.setItem('locale', response.data.preferred_language)
      }

      // Apply server-side theme preference
      if (response.data.theme) {
        usePalette().value = response.data.theme as Palette
      }

      // Resolve the selected event (best-effort, non-blocking)
      void loadSelectedEvent(response.data.selected_event_id ?? null)

      return response.data
    })()

    try {
      return await profilePromise
    } catch (error) {
      console.error('Error loading user profile:', error)
      throw error
    } finally {
      profileLoading.value = false
      profilePromise = null
    }
  }

  const ensureProfile = async () => {
    if (profile.value) return profile.value
    return await loadProfile()
  }

  const callProtectedAPI = async (endpoint: string, options: RequestInit = {}) => {
    try {
      const token = await getAccessToken()
      return await fetch(`${import.meta.env.VITE_API_URL}${endpoint}`, {
        ...options,
        headers: {
          ...options.headers,
          Authorization: `Bearer ${token}`,
        },
      })
    } catch (error) {
      console.error('Error calling protected API:', error)
      throw error
    }
  }

  /**
   * Nudge the user about join requests waiting on them.
   *
   * Replaces the old platform-wide "users pending approval" prompt: with open
   * signup there is nothing to approve at the account level, only at the event
   * level — and that lands on whoever runs the event, not on the superadmin.
   */
  const notifyPendingJoinRequests = (count: number) => {
    pendingJoinRequestCount.value = count
    if (count <= 0 || joinRequestToastShown) return
    joinRequestToastShown = true
    // Held rather than dropped while a guided tour is on screen. `loadFeed()`
    // fires this the moment the organiser's dashboard settles, which is exactly
    // when the tour's first step lands: an `Infinity`-duration toast then sits
    // over the popover *and* has both its buttons killed by driver's
    // `.driver-active * { pointer-events: none }`, so the visitor's first act
    // inside the product is a click that does nothing. Outside a tour —
    // every visit but a demo's first — `whenTourIsOver` is a plain call.
    whenTourIsOver(() => {
      toast.custom(markRaw(ActionToast), {
        duration: Infinity,
        componentProps: {
          message: t('dashboard.home.joinRequestToast.message', { count }, count),
          actionLabel: t('dashboard.home.joinRequestToast.action'),
          dismissLabel: t('dashboard.home.joinRequestToast.dismiss'),
          onAction: () => router.push({ name: 'my-events', query: { tab: 'requests' } }),
        },
      })
    })
  }

  watch(isAuthenticated, (next) => {
    if (!next) {
      profile.value = null
      selectedEvent.value = null
    }
  })

  return {
    approvalStatus,
    isApproved,
    session,
    isAuthenticated,
    user,
    profile,
    roles,
    isActive,
    isAdmin,
    isEventManager,
    eventRoles,
    myEventIds,
    managedEventIds,
    isManager,
    eventRole,
    canManageEvent,
    isEventOwner,
    isEventMember,
    pendingJoinRequestCount,
    notifyPendingJoinRequests,
    loading,
    profileLoading,
    selectedEventId,
    selectedEvent,
    logout,
    getAccessToken,
    updateUser,
    loadProfile,
    ensureProfile,
    setSelectedEvent,
    callProtectedAPI,
  }
})
