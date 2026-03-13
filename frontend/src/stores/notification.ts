import { computed, ref } from 'vue'

import { defineStore } from 'pinia'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

export interface NotificationType {
  id: string
  code: string
  name: string
  description: string | null
  category: string
  is_admin_only: boolean
  default_channels: string[]
  is_active: boolean
}

export interface NotificationItem {
  id: string
  recipient_id: string
  notification_type_code: string
  title: string
  body: string
  data: Record<string, unknown> | null
  is_read: boolean
  read_at: string | null
  channels_sent: string[]
  channels_failed: string[]
  created_at: string
}

export interface NotificationSubscription {
  id: string
  user_id: string
  notification_type_id: string
  email_enabled: boolean
  push_enabled: boolean
  telegram_enabled: boolean
  scope_type: string
  scope_id: string | null
  is_muted: boolean
  created_at: string
  updated_at: string
}

export interface TelegramBinding {
  id: string
  telegram_chat_id: string | null
  telegram_username: string | null
  is_verified: boolean
  created_at: string
}

export interface PushSubscriptionInfo {
  id: string
  endpoint: string
  user_agent: string | null
  created_at: string
}

export const useNotificationStore = defineStore('notification', () => {
  const { get, post, put, patch, delete: del } = useAuthenticatedClient()

  const notifications = ref<NotificationItem[]>([])
  const unreadCount = ref(0)
  const notificationTypes = ref<NotificationType[]>([])
  const preferences = ref<NotificationSubscription[]>([])
  const telegramBinding = ref<TelegramBinding | null>(null)
  const pushSubscriptions = ref<PushSubscriptionInfo[]>([])
  const loading = ref(false)

  let pollInterval: ReturnType<typeof setInterval> | null = null

  const hasUnread = computed(() => unreadCount.value > 0)

  // ── Notification feed ──────────────────────────────────────────

  async function fetchUnreadCount() {
    try {
      const res = await get<{ unread_count: number }>({
        url: '/notifications/unread-count',
      })
      unreadCount.value = res.data.unread_count
    } catch (error) {
      console.error('Failed to fetch unread count:', error)
    }
  }

  async function fetchNotifications(options?: { unreadOnly?: boolean; skip?: number; limit?: number }) {
    loading.value = true
    try {
      const params: Record<string, unknown> = {}
      if (options?.unreadOnly) params.unread_only = true
      if (options?.skip) params.skip = options.skip
      if (options?.limit) params.limit = options.limit

      const res = await get<{
        items: NotificationItem[]
        total: number
        unread_count: number
        skip: number
        limit: number
      }>({
        url: '/notifications/',
        query: params,
      })
      const data = res.data
      notifications.value = data.items
      unreadCount.value = data.unread_count
      return data
    } catch (error) {
      console.error('Failed to fetch notifications:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function markAsRead(notificationId: string) {
    try {
      const res = await patch<NotificationItem>({
        url: `/notifications/${notificationId}/read`,
      })
      const updated = res.data
      const idx = notifications.value.findIndex((n) => n.id === notificationId)
      if (idx !== -1) {
        notifications.value[idx] = updated
      }
      unreadCount.value = Math.max(0, unreadCount.value - 1)
      return updated
    } catch (error) {
      console.error('Failed to mark notification as read:', error)
      throw error
    }
  }

  async function markAllAsRead() {
    try {
      await post<{ marked_count: number }>({
        url: '/notifications/mark-all-read',
      })
      notifications.value = notifications.value.map((n) => ({ ...n, is_read: true }))
      unreadCount.value = 0
    } catch (error) {
      console.error('Failed to mark all as read:', error)
      throw error
    }
  }

  async function dismissNotification(notificationId: string) {
    try {
      await del({ url: `/notifications/${notificationId}` })
      notifications.value = notifications.value.filter((n) => n.id !== notificationId)
    } catch (error) {
      console.error('Failed to dismiss notification:', error)
      throw error
    }
  }

  // ── Notification types ─────────────────────────────────────────

  async function fetchNotificationTypes() {
    try {
      const res = await get<NotificationType[]>({
        url: '/notifications/types',
      })
      notificationTypes.value = res.data
      return res.data
    } catch (error) {
      console.error('Failed to fetch notification types:', error)
      throw error
    }
  }

  // ── Preferences ────────────────────────────────────────────────

  async function fetchPreferences() {
    try {
      const res = await get<NotificationSubscription[]>({
        url: '/notifications/preferences',
      })
      preferences.value = res.data
      return res.data
    } catch (error) {
      console.error('Failed to fetch preferences:', error)
      throw error
    }
  }

  async function updatePreferences(
    prefs: Array<{
      notification_type_id: string
      email_enabled: boolean
      push_enabled: boolean
      telegram_enabled: boolean
      scope_type?: string
      scope_id?: string | null
      is_muted?: boolean
    }>,
  ) {
    try {
      const res = await put<NotificationSubscription[]>({
        url: '/notifications/preferences',
        body: { preferences: prefs },
      })
      preferences.value = res.data
      return res.data
    } catch (error) {
      console.error('Failed to update preferences:', error)
      throw error
    }
  }

  // ── Push subscriptions ─────────────────────────────────────────

  async function fetchVapidPublicKey(): Promise<string | null> {
    try {
      const res = await get<{ vapid_public_key: string }>({
        url: '/notifications/vapid-public-key',
      })
      return res.data.vapid_public_key
    } catch {
      return null
    }
  }

  async function registerPushSubscription(subscription: PushSubscription) {
    const json = subscription.toJSON()
    try {
      await post({
        url: '/notifications/push-subscriptions',
        body: {
          endpoint: json.endpoint,
          p256dh_key: json.keys?.p256dh ?? '',
          auth_key: json.keys?.auth ?? '',
          user_agent: navigator.userAgent,
        },
      })
    } catch (error) {
      console.error('Failed to register push subscription:', error)
      throw error
    }
  }

  async function fetchPushSubscriptions() {
    try {
      const res = await get<PushSubscriptionInfo[]>({
        url: '/notifications/push-subscriptions',
      })
      pushSubscriptions.value = res.data
      return res.data
    } catch (error) {
      console.error('Failed to fetch push subscriptions:', error)
      throw error
    }
  }

  // ── Telegram ───────────────────────────────────────────────────

  async function fetchTelegramBinding() {
    try {
      const res = await get<TelegramBinding | null>({
        url: '/notifications/telegram',
      })
      telegramBinding.value = res.data
      return res.data
    } catch {
      telegramBinding.value = null
      return null
    }
  }

  async function startTelegramBinding() {
    try {
      const res = await post<{
        verification_code: string
        bot_username: string | null
        expires_at: string
      }>({
        url: '/notifications/telegram/bind',
      })
      return res.data
    } catch (error) {
      console.error('Failed to start Telegram binding:', error)
      throw error
    }
  }

  async function verifyTelegramBinding(code: string, chatId: string, username?: string) {
    try {
      const res = await post<TelegramBinding>({
        url: '/notifications/telegram/verify',
        body: {
          verification_code: code,
          telegram_chat_id: chatId,
          telegram_username: username,
        },
      })
      telegramBinding.value = res.data
      return res.data
    } catch (error) {
      console.error('Failed to verify Telegram binding:', error)
      throw error
    }
  }

  async function unbindTelegram() {
    try {
      await del({ url: '/notifications/telegram' })
      telegramBinding.value = null
    } catch (error) {
      console.error('Failed to unbind Telegram:', error)
      throw error
    }
  }

  // ── Polling ────────────────────────────────────────────────────

  function startPolling(intervalMs = 30000) {
    stopPolling()
    fetchUnreadCount()
    pollInterval = setInterval(fetchUnreadCount, intervalMs)
  }

  function stopPolling() {
    if (pollInterval) {
      clearInterval(pollInterval)
      pollInterval = null
    }
  }

  return {
    // State
    notifications,
    unreadCount,
    notificationTypes,
    preferences,
    telegramBinding,
    pushSubscriptions,
    loading,
    hasUnread,

    // Feed
    fetchUnreadCount,
    fetchNotifications,
    markAsRead,
    markAllAsRead,
    dismissNotification,

    // Types
    fetchNotificationTypes,

    // Preferences
    fetchPreferences,
    updatePreferences,

    // Push
    fetchVapidPublicKey,
    registerPushSubscription,
    fetchPushSubscriptions,

    // Telegram
    fetchTelegramBinding,
    startTelegramBinding,
    verifyTelegramBinding,
    unbindTelegram,

    // Polling
    startPolling,
    stopPolling,
  }
})
