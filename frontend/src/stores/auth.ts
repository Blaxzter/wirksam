import { computed, markRaw, ref, watch } from 'vue'

import { useAuth0 } from '@auth0/auth0-vue'
import type { User } from '@auth0/auth0-vue'
import { defineStore } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import ActionToast from '@/components/ui/sonner/ActionToast.vue'

import type { UserProfile, UserRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'

export type { User }

export const useAuthStore = defineStore('auth', () => {
  const auth0 = useAuth0()
  const { post, get } = useAuthenticatedClient()
  const { t } = useI18n()
  const router = useRouter()
  const loading = ref(false)
  const profileLoading = ref(false)
  const pendingUserCount = ref(0)

  const isAuthenticated = computed(() => auth0.isAuthenticated.value)
  const user = computed(() => auth0.user.value)
  const profile = ref<UserProfile | null>(null)
  const roles = computed(() => profile.value?.roles ?? [])
  const isAdmin = computed(() => profile.value?.is_admin ?? false)
  const isActive = computed(() => profile.value?.is_active ?? true)

  let profilePromise: Promise<UserProfile | null> | null = null

  const logout = () => {
    profile.value = null
    auth0.logout({
      logoutParams: {
        returnTo: window.location.origin,
      },
    })
  }

  const getAccessToken = async () => {
    try {
      return await auth0.getAccessTokenSilently()
    } catch (error) {
      console.error('Error getting access token:', error)
      throw error
    }
  }

  const updateUser = (userData: Partial<User>) => {
    console.log('Updating user with data:', userData)

    if (!isAuthenticated.value || !auth0.user.value) return

    auth0.user.value = {
      ...auth0.user.value,
      ...userData,
    }
  }

  const loadProfile = async () => {
    if (!isAuthenticated.value) return null
    if (profilePromise) return await profilePromise

    profileLoading.value = true
    profilePromise = (async () => {
      // Send profile data from Auth0 ID token to backend for user initialization
      const profileInit =
        auth0.user.value && (auth0.user.value.email || auth0.user.value.name)
          ? {
              email: auth0.user.value.email,
              name: auth0.user.value.name,
              nickname: auth0.user.value.nickname,
              picture: auth0.user.value.picture,
              email_verified: auth0.user.value.email_verified,
              preferred_language: i18n.global.locale.value,
            }
          : null

      const response = await post<{ data: UserProfile }>({
        url: '/users/me',
        body: profileInit,
      })
      profile.value = response.data

      // Apply server-side language preference
      if (response.data.preferred_language) {
        i18n.global.locale.value = response.data.preferred_language as 'en' | 'de'
        localStorage.setItem('locale', response.data.preferred_language)
      }

      // Check for pending users once per session (admin only)
      if (response.data.is_admin) {
        checkPendingUsers()
      }

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

  const checkPendingUsers = async () => {
    try {
      const usersRes = await get<{ data: UserRead[] }>({ url: '/users/' })
      const pending = usersRes.data.filter((u) => !u.is_active && !u.rejection_reason)
      pendingUserCount.value = pending.length
      if (pending.length > 0) {
        toast.custom(markRaw(ActionToast), {
          duration: Infinity,
          componentProps: {
            message: t(
              'dashboard.home.stats.users.pendingToast',
              { count: pending.length },
              pending.length,
            ),
            actionLabel: t('dashboard.home.stats.users.pendingAction'),
            dismissLabel: t('dashboard.home.stats.users.pendingDismiss'),
            onAction: () => router.push({ name: 'admin-users' }),
          },
        })
      }
    } catch {
      // Non-critical, ignore
    }
  }

  watch(isAuthenticated, (next) => {
    if (!next) {
      profile.value = null
    }
  })

  return {
    auth0,
    isAuthenticated,
    user,
    profile,
    roles,
    isActive,
    isAdmin,
    pendingUserCount,
    loading,
    profileLoading,
    logout,
    getAccessToken,
    updateUser,
    loadProfile,
    ensureProfile,
    callProtectedAPI,
  }
})
