<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { Bell, ExternalLink, Mail, MessageCircle, Smartphone, TriangleAlert } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import type { NotificationSubscription, NotificationType } from '@/stores/notification'
import { useNotificationStore } from '@/stores/notification'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'

import TelegramLoginWidget from '@/components/account/TelegramLoginWidget.vue'

const { t } = useI18n()
const notificationStore = useNotificationStore()

const loading = ref(true)
const saving = ref(false)
const types = ref<NotificationType[]>([])
const preferences = ref<Map<string, { email: boolean; push: boolean; telegram: boolean }>>(
  new Map(),
)

// Global channel toggles (backed by user-level settings on the server)
const globalChannelSettings = computed(() => notificationStore.globalChannelSettings)

async function toggleGlobalChannel(
  field: 'notify_email' | 'notify_push' | 'notify_telegram',
  enabled: boolean,
) {
  try {
    await notificationStore.updateGlobalChannelSettings({ [field]: enabled })
  } catch {
    toast.error(t('notifications.preferences.saveFailed'))
  }
}

// Group types by category
const groupedTypes = computed(() => {
  const groups: Record<string, NotificationType[]> = {}
  for (const type of types.value) {
    if (!groups[type.category]) {
      groups[type.category] = []
    }
    groups[type.category].push(type)
  }
  return groups
})

const categoryLabels: Record<string, string> = {
  booking: 'notifications.categories.booking',
  slot: 'notifications.categories.slot',
  event: 'notifications.categories.event',
  event_group: 'notifications.categories.eventGroup',
  availability: 'notifications.categories.availability',
  admin: 'notifications.categories.admin',
  user: 'notifications.categories.user',
}

function getCategoryLabel(category: string): string {
  const key = categoryLabels[category]
  return key ? t(key) : category
}

function getPreference(typeId: string) {
  return preferences.value.get(typeId) || { email: true, push: true, telegram: false }
}

function setPreference(typeId: string, channel: 'email' | 'push' | 'telegram', value: boolean) {
  const current = getPreference(typeId)
  preferences.value.set(typeId, { ...current, [channel]: value })
}

async function savePreferences() {
  saving.value = true
  try {
    const prefs = types.value.map((type) => {
      const pref = getPreference(type.id)
      return {
        notification_type_id: type.id,
        email_enabled: pref.email,
        push_enabled: pref.push,
        telegram_enabled: pref.telegram,
        scope_type: 'global' as const,
        scope_id: null,
        is_muted: false,
      }
    })
    await notificationStore.updatePreferences(prefs)
    toast.success(t('notifications.preferences.saved'))
  } catch {
    toast.error(t('notifications.preferences.saveFailed'))
  } finally {
    saving.value = false
  }
}

// ── Push notification management ─────────────────────────────────

const pushSupported = ref(false)
const pushPermission = ref<NotificationPermission>('default')

async function requestPushPermission() {
  try {
    const permission = await Notification.requestPermission()
    pushPermission.value = permission

    if (permission === 'granted') {
      const vapidKey = await notificationStore.fetchVapidPublicKey()
      if (!vapidKey) {
        toast.error(t('notifications.push.notConfigured'))
        return
      }

      const registration = await navigator.serviceWorker.ready
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidKey),
      })

      await notificationStore.registerPushSubscription(subscription)
      toast.success(t('notifications.push.enabled'))
    }
  } catch (error) {
    console.error('Push registration failed:', error)
    toast.error(t('notifications.push.failed'))
  }
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(base64)
  const outputArray = new Uint8Array(rawData.length)
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i)
  }
  return outputArray
}

// ── Telegram management ──────────────────────────────────────────

const telegramBinding = computed(() => notificationStore.telegramBinding)
const telegramBotUsername = computed(() => notificationStore.telegramBotUsername)
const telegramConfigured = computed(() => notificationStore.telegramConfigured)
const connectingTelegram = ref(false)

const telegramNotConnectedWarning = computed(() => {
  if (telegramBinding.value?.is_verified) return false
  return globalChannelSettings.value.notify_telegram
})

// Manual code fallback
const telegramCode = ref<string | null>(null)
const manualBotUsername = ref<string | null>(null)
const bindingTelegram = ref(false)
let telegramPollTimer: ReturnType<typeof setInterval> | null = null

const telegramDeepLink = computed(() => {
  if (!telegramCode.value || !manualBotUsername.value) return null
  return `https://t.me/${manualBotUsername.value}?start=${telegramCode.value}`
})

const botStartLink = computed(() => {
  if (!telegramBotUsername.value) return null
  return `https://t.me/${telegramBotUsername.value}`
})

async function onTelegramAuth(data: {
  id: number
  first_name?: string
  last_name?: string
  username?: string
  photo_url?: string
  auth_date: number
  hash: string
}) {
  connectingTelegram.value = true
  try {
    await notificationStore.loginWithTelegram(data)
    toast.success(t('notifications.telegram.connected'))
  } catch {
    toast.error(t('notifications.telegram.authFailed'))
  } finally {
    connectingTelegram.value = false
  }
}

function startTelegramPolling() {
  stopTelegramPolling()
  telegramPollTimer = setInterval(async () => {
    await notificationStore.fetchTelegramBinding()
    if (telegramBinding.value?.is_verified) {
      stopTelegramPolling()
      telegramCode.value = null
      toast.success(t('notifications.telegram.connected'))
    }
  }, 3000)
}

function stopTelegramPolling() {
  if (telegramPollTimer) {
    clearInterval(telegramPollTimer)
    telegramPollTimer = null
  }
}

async function startManualTelegramBinding() {
  bindingTelegram.value = true
  try {
    const result = await notificationStore.startTelegramBinding()
    telegramCode.value = result.verification_code
    manualBotUsername.value = result.bot_username
    startTelegramPolling()
  } catch {
    toast.error(t('notifications.telegram.bindFailed'))
  } finally {
    bindingTelegram.value = false
  }
}

async function unbindTelegram() {
  try {
    await notificationStore.unbindTelegram()
    telegramCode.value = null
    stopTelegramPolling()
    toast.success(t('notifications.telegram.unbound'))
  } catch {
    toast.error(t('notifications.telegram.unbindFailed'))
  }
}

// ── Lifecycle ────────────────────────────────────────────────────

onUnmounted(() => stopTelegramPolling())

onMounted(async () => {
  try {
    // Check push support
    pushSupported.value = 'serviceWorker' in navigator && 'PushManager' in window
    if (pushSupported.value) {
      pushPermission.value = Notification.permission
    }

    // Load data
    const [typesData, prefsData] = await Promise.all([
      notificationStore.fetchNotificationTypes(),
      notificationStore.fetchPreferences(),
      notificationStore.fetchTelegramBinding(),
      notificationStore.fetchTelegramConfig(),
      notificationStore.fetchGlobalChannelSettings(),
    ])

    types.value = typesData

    // Build preferences map from existing subscriptions
    const prefMap = new Map<string, { email: boolean; push: boolean; telegram: boolean }>()
    for (const pref of prefsData as NotificationSubscription[]) {
      if (pref.scope_type === 'global') {
        prefMap.set(pref.notification_type_id, {
          email: pref.email_enabled,
          push: pref.push_enabled,
          telegram: pref.telegram_enabled,
        })
      }
    }

    // Fill in defaults for types without preferences
    for (const type of typesData as NotificationType[]) {
      if (!prefMap.has(type.id)) {
        prefMap.set(type.id, {
          email: type.default_channels.includes('email'),
          push: type.default_channels.includes('push'),
          telegram: type.default_channels.includes('telegram'),
        })
      }
    }

    preferences.value = prefMap
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-6">
    <!-- Header -->
    <div class="pb-3">
      <h1 class="text-3xl font-bold tracking-tight break-words">
        {{ t('notifications.preferences.title') }}
      </h1>
      <p class="text-muted-foreground mt-2">
        {{ t('notifications.preferences.subtitle') }}
      </p>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-12">
      <div class="border-primary h-8 w-8 animate-spin rounded-full border-2 border-t-transparent" />
    </div>

    <template v-else>
      <!-- Push notification setup -->
      <Card v-if="pushSupported">
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Smartphone class="h-5 w-5" />
            {{ t('notifications.push.title') }}
          </CardTitle>
          <CardDescription>
            {{ t('notifications.push.description') }}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div v-if="pushPermission === 'granted'" class="flex items-center gap-2">
            <Badge variant="outline" class="text-green-600">
              {{ t('notifications.push.enabled') }}
            </Badge>
          </div>
          <div v-else-if="pushPermission === 'denied'" class="text-muted-foreground text-sm">
            {{ t('notifications.push.denied') }}
          </div>
          <Button v-else variant="outline" @click="requestPushPermission">
            {{ t('notifications.push.enable') }}
          </Button>
        </CardContent>
      </Card>

      <!-- Telegram binding -->
      <Card v-if="telegramConfigured">
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <MessageCircle class="h-5 w-5" />
            {{ t('notifications.telegram.title') }}
          </CardTitle>
          <CardDescription>
            {{ t('notifications.telegram.description') }}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <!-- Warning: Telegram enabled but not connected -->
          <div
            v-if="telegramNotConnectedWarning && !telegramBinding?.is_verified"
            class="bg-amber-50 dark:bg-amber-950/30 text-amber-800 dark:text-amber-200 mb-4 flex items-start gap-2 rounded-lg border border-amber-200 dark:border-amber-800 p-3 text-sm"
          >
            <TriangleAlert class="mt-0.5 h-4 w-4 shrink-0" />
            <span>{{ t('notifications.telegram.notConnectedWarning') }}</span>
          </div>

          <!-- Connected state -->
          <div v-if="telegramBinding?.is_verified" class="space-y-3">
            <div class="flex items-center gap-2">
              <Badge variant="outline" class="text-green-600">
                {{ t('notifications.telegram.connected') }}
              </Badge>
              <span v-if="telegramBinding.telegram_username" class="text-muted-foreground text-sm">
                @{{ telegramBinding.telegram_username }}
              </span>
            </div>
            <p v-if="botStartLink" class="text-muted-foreground text-sm">
              {{ t('notifications.telegram.startBotHint') }}
              <a
                :href="botStartLink"
                target="_blank"
                rel="noopener noreferrer"
                class="text-primary underline underline-offset-2"
              >
                @{{ telegramBotUsername }}
              </a>
            </p>
            <Button variant="outline" size="sm" @click="unbindTelegram">
              {{ t('notifications.telegram.disconnect') }}
            </Button>
          </div>

          <!-- Not connected: show Login Widget or manual fallback -->
          <div v-else class="space-y-4">
            <!-- Telegram Login Widget (primary) -->
            <div v-if="telegramBotUsername && !telegramCode">
              <p class="text-muted-foreground mb-3 text-sm">
                {{ t('notifications.telegram.loginDescription') }}
              </p>
              <TelegramLoginWidget :bot-username="telegramBotUsername" @auth="onTelegramAuth" />
              <div v-if="connectingTelegram" class="text-muted-foreground mt-2 text-sm">
                {{ t('notifications.telegram.connecting') }}
              </div>
            </div>

            <!-- Manual code fallback (collapsed) -->
            <details class="text-sm">
              <summary class="text-muted-foreground cursor-pointer text-xs">
                {{ t('notifications.telegram.manualFallback') }}
              </summary>
              <div class="mt-3 space-y-3">
                <div v-if="telegramCode" class="space-y-3">
                  <a
                    v-if="telegramDeepLink"
                    :href="telegramDeepLink"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="bg-primary text-primary-foreground hover:bg-primary/90 inline-flex items-center rounded-md px-4 py-2 text-sm font-medium"
                  >
                    <ExternalLink class="mr-2 h-4 w-4" />
                    {{ t('notifications.telegram.openInTelegram') }}
                  </a>
                  <p class="text-muted-foreground text-sm">
                    {{ t('notifications.telegram.waitingForVerification') }}
                  </p>
                  <div class="space-y-2">
                    <p class="text-muted-foreground text-xs">
                      {{ t('notifications.telegram.sendCode') }}
                    </p>
                    <div class="bg-muted rounded-lg p-3 text-center">
                      <code class="text-sm font-bold">{{ telegramCode }}</code>
                    </div>
                    <p v-if="manualBotUsername" class="text-muted-foreground text-xs">
                      {{ t('notifications.telegram.sendTo') }}
                      <strong>@{{ manualBotUsername }}</strong>
                    </p>
                  </div>
                </div>
                <Button
                  v-else
                  variant="outline"
                  size="sm"
                  :disabled="bindingTelegram"
                  @click="startManualTelegramBinding"
                >
                  {{ t('notifications.telegram.connectManually') }}
                </Button>
              </div>
            </details>
          </div>
        </CardContent>
      </Card>

      <!-- Global channel toggles -->
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Bell class="h-5 w-5" />
            {{ t('notifications.globalToggle.title') }}
          </CardTitle>
          <CardDescription>
            {{ t('notifications.globalToggle.description') }}
          </CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="flex items-center justify-between">
            <div class="space-y-0.5">
              <Label class="text-sm font-medium">{{
                t('notifications.globalToggle.emailLabel')
              }}</Label>
              <p class="text-muted-foreground text-xs">
                {{ t('notifications.globalToggle.emailDescription') }}
              </p>
            </div>
            <Switch
              :model-value="globalChannelSettings.notify_email"
              @update:model-value="(v: boolean) => toggleGlobalChannel('notify_email', v)"
            />
          </div>
          <Separator />
          <div class="flex items-center justify-between">
            <div class="space-y-0.5">
              <Label class="text-sm font-medium">{{
                t('notifications.globalToggle.pushLabel')
              }}</Label>
              <p class="text-muted-foreground text-xs">
                {{ t('notifications.globalToggle.pushDescription') }}
              </p>
            </div>
            <Switch
              :model-value="globalChannelSettings.notify_push"
              @update:model-value="(v: boolean) => toggleGlobalChannel('notify_push', v)"
            />
          </div>
          <Separator />
          <div class="flex items-center justify-between">
            <div class="space-y-0.5">
              <Label class="text-sm font-medium">{{
                t('notifications.globalToggle.telegramLabel')
              }}</Label>
              <p class="text-muted-foreground text-xs">
                {{ t('notifications.globalToggle.telegramDescription') }}
              </p>
              <p
                v-if="telegramNotConnectedWarning"
                class="flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400"
              >
                <TriangleAlert class="h-3 w-3 shrink-0" />
                {{ t('notifications.telegram.notConnectedShort') }}
              </p>
            </div>
            <Switch
              :model-value="globalChannelSettings.notify_telegram"
              @update:model-value="(v: boolean) => toggleGlobalChannel('notify_telegram', v)"
            />
          </div>
        </CardContent>
      </Card>

      <!-- Notification type preferences -->
      <Card v-for="(categoryTypes, category) in groupedTypes" :key="category">
        <CardHeader>
          <CardTitle>{{ getCategoryLabel(category as string) }}</CardTitle>
        </CardHeader>
        <CardContent class="space-y-0">
          <!-- Column headers -->
          <div
            class="text-muted-foreground mb-3 flex items-center gap-2 sm:gap-4 text-xs font-medium"
          >
            <div class="min-w-0 flex-1" />
            <div class="flex w-10 sm:w-24 items-center justify-center gap-1">
              <Mail class="h-3.5 w-3.5 shrink-0" />
              <span class="hidden sm:inline">{{ t('notifications.channels.email') }}</span>
            </div>
            <div class="flex w-10 sm:w-24 items-center justify-center gap-1">
              <Smartphone class="h-3.5 w-3.5 shrink-0" />
              <span class="hidden sm:inline">{{ t('notifications.channels.push') }}</span>
            </div>
            <div class="flex w-10 sm:w-24 items-center justify-center gap-1">
              <MessageCircle class="h-3.5 w-3.5 shrink-0" />
              <span class="hidden sm:inline">{{ t('notifications.channels.telegram') }}</span>
            </div>
          </div>

          <Separator />

          <div
            v-for="type in categoryTypes as NotificationType[]"
            :key="type.id"
            class="flex items-center gap-2 sm:gap-4 py-3"
          >
            <div class="min-w-0 flex-1">
              <p class="text-sm font-medium">{{ type.name }}</p>
              <p v-if="type.description" class="text-muted-foreground text-xs">
                {{ type.description }}
              </p>
              <Badge v-if="type.is_admin_only" variant="secondary" class="mt-1 text-[10px]">
                {{ t('notifications.adminOnly') }}
              </Badge>
            </div>
            <div class="flex w-10 sm:w-24 justify-center">
              <Switch
                :model-value="getPreference(type.id).email"
                @update:model-value="(v: boolean) => setPreference(type.id, 'email', v)"
              />
            </div>
            <div class="flex w-10 sm:w-24 justify-center">
              <Switch
                :model-value="getPreference(type.id).push"
                @update:model-value="(v: boolean) => setPreference(type.id, 'push', v)"
              />
            </div>
            <div class="flex w-10 sm:w-24 justify-center">
              <Switch
                :model-value="getPreference(type.id).telegram"
                @update:model-value="(v: boolean) => setPreference(type.id, 'telegram', v)"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <!-- Save button -->
      <div class="flex justify-end">
        <Button :disabled="saving" @click="savePreferences">
          <Bell class="mr-2 h-4 w-4" />
          {{ t('notifications.preferences.save') }}
        </Button>
      </div>
    </template>
  </div>
</template>
