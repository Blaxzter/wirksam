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

export interface GlobalChannelSettings {
  notify_email: boolean
  notify_push: boolean
  notify_telegram: boolean
}

export interface PushSubscriptionInfo {
  id: string
  endpoint: string
  user_agent: string | null
  created_at: string
}

export const useNotificationStore = defineStore('notification', () => {
  const { get, post, put, patch, delete: del, getAuthToken } = useAuthenticatedClient()

  const notifications = ref<NotificationItem[]>([])
  const unreadCount = ref(0)
  const total = ref(0)
  const hasMore = computed(() => notifications.value.length < total.value)
  const notificationTypes = ref<NotificationType[]>([])
  const preferences = ref<NotificationSubscription[]>([])
  const telegramBinding = ref<TelegramBinding | null>(null)
  const pushSubscriptions = ref<PushSubscriptionInfo[]>([])
  const globalChannelSettings = ref<GlobalChannelSettings>({
    notify_email: true,
    notify_push: true,
    notify_telegram: true,
  })
  const loading = ref(false)

  let eventSource: EventSource | null = null
  let pollInterval: ReturnType<typeof setInterval> | null = null
  let reconnectTimeout: ReturnType<typeof setTimeout> | null = null
  let reconnectDelay = 1000 // starts at 1s, doubles on each failure

  const hasUnread = computed(() => unreadCount.value > 0)

  // ── Notification feed ──────────────────────────────────────────

  async function fetchUnreadCount() {
    try {
      const res = await get<{ data: { unread_count: number } }>({
        url: '/notifications/unread-count',
      })
      unreadCount.value = res.data.unread_count
    } catch (error) {
      console.error('Failed to fetch unread count:', error)
    }
  }

  async function fetchNotifications(options?: {
    unreadOnly?: boolean
    skip?: number
    limit?: number
    append?: boolean
  }) {
    loading.value = true
    try {
      const params: Record<string, unknown> = {}
      if (options?.unreadOnly) params.unread_only = true
      if (options?.skip !== undefined) params.skip = options.skip
      if (options?.limit) params.limit = options.limit

      const res = await get<{
        data: {
          items: NotificationItem[]
          total: number
          unread_count: number
          skip: number
          limit: number
        }
      }>({
        url: '/notifications/',
        query: params,
      })
      if (options?.append) {
        notifications.value = [...notifications.value, ...res.data.items]
      } else {
        notifications.value = res.data.items
      }
      total.value = res.data.total
      unreadCount.value = res.data.unread_count
      return res.data
    } catch (error) {
      console.error('Failed to fetch notifications:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function loadMoreNotifications() {
    if (!hasMore.value || loading.value) return
    await fetchNotifications({ skip: notifications.value.length, limit: 20, append: true })
  }

  async function markAsRead(notificationId: string) {
    try {
      const res = await patch<{ data: NotificationItem }>({
        url: `/notifications/${notificationId}/read`,
      })
      const idx = notifications.value.findIndex((n) => n.id === notificationId)
      if (idx !== -1) {
        notifications.value[idx] = res.data
      }
      unreadCount.value = Math.max(0, unreadCount.value - 1)
      return res.data
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
      const res = await get<{ data: NotificationType[] }>({
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
      const res = await get<{ data: NotificationSubscription[] }>({
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
      const res = await put<{ data: NotificationSubscription[] }>({
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

  // ── Global channel settings ──────────────────────────────────

  async function fetchGlobalChannelSettings() {
    try {
      const res = await get<{ data: GlobalChannelSettings }>({
        url: '/notifications/channel-settings',
      })
      globalChannelSettings.value = res.data
      return res.data
    } catch (error) {
      console.error('Failed to fetch global channel settings:', error)
      throw error
    }
  }

  async function updateGlobalChannelSettings(settings: Partial<GlobalChannelSettings>) {
    try {
      const res = await patch<{ data: GlobalChannelSettings }>({
        url: '/notifications/channel-settings',
        body: settings,
      })
      globalChannelSettings.value = res.data
      return res.data
    } catch (error) {
      console.error('Failed to update global channel settings:', error)
      throw error
    }
  }

  // ── Push subscriptions ─────────────────────────────────────────

  async function fetchVapidPublicKey(): Promise<string | null> {
    try {
      const res = await get<{ data: { vapid_public_key: string } }>({
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
      const res = await get<{ data: PushSubscriptionInfo[] }>({
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

  const telegramBotUsername = ref<string | null>(null)
  const telegramConfigured = ref(false)

  async function fetchTelegramConfig() {
    try {
      const res = await get<{ data: { bot_username: string | null; is_configured: boolean } }>({
        url: '/notifications/telegram/config',
      })
      telegramBotUsername.value = res.data.bot_username
      telegramConfigured.value = res.data.is_configured
      return res.data
    } catch {
      telegramConfigured.value = false
      return null
    }
  }

  async function fetchTelegramBinding() {
    try {
      const res = await get<{ data: TelegramBinding | null }>({
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
        data: {
          verification_code: string
          bot_username: string | null
          expires_at: string
        }
      }>({
        url: '/notifications/telegram/bind',
      })
      return res.data
    } catch (error) {
      console.error('Failed to start Telegram binding:', error)
      throw error
    }
  }

  async function loginWithTelegram(data: {
    id: number
    first_name?: string
    last_name?: string
    username?: string
    photo_url?: string
    auth_date: number
    hash: string
  }) {
    try {
      const res = await post<{ data: TelegramBinding }>({
        url: '/notifications/telegram/login',
        body: data,
      })
      telegramBinding.value = res.data
      return res.data
    } catch (error) {
      console.error('Failed to login with Telegram:', error)
      throw error
    }
  }

  async function verifyTelegramBinding(code: string, chatId: string, username?: string) {
    try {
      const res = await post<{ data: TelegramBinding }>({
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

  // ── SSE stream (with polling fallback) ────────────────────────

  async function startStream() {
    stopStream()

    let token: string
    try {
      token = await getAuthToken()
    } catch {
      // Not authenticated yet — fall back to polling
      startPollingFallback()
      return
    }

    const baseUrl = import.meta.env.VITE_API_URL
    const url = `${baseUrl}/notifications/stream?token=${encodeURIComponent(token)}`

    eventSource = new EventSource(url)

    eventSource.addEventListener('unread_count', (e: MessageEvent) => {
      try {
        const payload = JSON.parse(e.data) as { unread_count: number }
        unreadCount.value = payload.unread_count
      } catch {
        console.error('Failed to parse SSE unread_count event')
      }
    })

    eventSource.onopen = () => {
      // Connection established — reset backoff and stop any polling fallback
      reconnectDelay = 1000
      stopPollingFallback()
    }

    eventSource.onerror = () => {
      // Close broken connection and schedule reconnect with backoff
      stopEventSource()
      startPollingFallback()

      reconnectTimeout = setTimeout(() => {
        reconnectTimeout = null
        startStream()
      }, reconnectDelay)
      reconnectDelay = Math.min(reconnectDelay * 2, 30000)
    }
  }

  function stopStream() {
    stopEventSource()
    stopPollingFallback()
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout)
      reconnectTimeout = null
    }
    reconnectDelay = 1000
  }

  function stopEventSource() {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
  }

  function startPollingFallback() {
    if (pollInterval) return // already polling
    fetchUnreadCount()
    pollInterval = setInterval(fetchUnreadCount, 30000)
  }

  function stopPollingFallback() {
    if (pollInterval) {
      clearInterval(pollInterval)
      pollInterval = null
    }
  }

  return {
    // State
    notifications,
    unreadCount,
    total,
    hasMore,
    notificationTypes,
    preferences,
    telegramBinding,
    pushSubscriptions,
    globalChannelSettings,
    loading,
    hasUnread,

    // Feed
    fetchUnreadCount,
    fetchNotifications,
    loadMoreNotifications,
    markAsRead,
    markAllAsRead,
    dismissNotification,

    // Types
    fetchNotificationTypes,

    // Preferences
    fetchPreferences,
    updatePreferences,

    // Global channel settings
    fetchGlobalChannelSettings,
    updateGlobalChannelSettings,

    // Push
    fetchVapidPublicKey,
    registerPushSubscription,
    fetchPushSubscriptions,

    // Telegram
    fetchTelegramConfig,
    fetchTelegramBinding,
    startTelegramBinding,
    loginWithTelegram,
    verifyTelegramBinding,
    unbindTelegram,
    telegramBotUsername,
    telegramConfigured,

    // Real-time updates
    startStream,
    stopStream,
  }
})
