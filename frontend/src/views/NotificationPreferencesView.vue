<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { Check, LoaderCircle } from 'lucide-vue-next'
import { useDebounceFn } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import type { NotificationSubscription, NotificationType } from '@/stores/notification'
import { useNotificationStore } from '@/stores/notification'
import type { ReminderOffsetEntry } from '@/stores/bookingReminder'
import { useBookingReminderStore } from '@/stores/bookingReminder'

import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'

import DefaultRemindersCard from '@/components/notifications/DefaultRemindersCard.vue'
import PerTypePreferencesSection from '@/components/notifications/PerTypePreferencesSection.vue'
import PushChannelCard from '@/components/notifications/PushChannelCard.vue'
import TelegramChannelCard from '@/components/notifications/TelegramChannelCard.vue'

import AnimatedMail from '@/components/icons/lucide-animated/Mail.vue'

const { t } = useI18n()
const notificationStore = useNotificationStore()
const reminderStore = useBookingReminderStore()

const loading = ref(true)
const types = ref<NotificationType[]>([])
const preferences = ref<Map<string, { email: boolean; push: boolean; telegram: boolean }>>(
  new Map(),
)

// Global channel toggles
const globalChannelSettings = computed(() => notificationStore.globalChannelSettings)

// Available reminder channels (hide telegram if not connected)
const telegramConnected = computed(() => notificationStore.telegramBinding?.is_verified ?? false)
const reminderChannels = computed(() => {
  const channels = ['email', 'push']
  if (telegramConnected.value) channels.push('telegram')
  return channels
})

const mailIconRef = ref<InstanceType<typeof AnimatedMail>>()

async function toggleGlobalChannel(
  field: 'notify_email' | 'notify_push' | 'notify_telegram',
  enabled: boolean,
) {
  try {
    await notificationStore.updateGlobalChannelSettings({ [field]: enabled })
    if (enabled && field === 'notify_email') mailIconRef.value?.startAnimation()
  } catch {
    toast.error(t('notifications.preferences.saveFailed'))
  }
}

// Per-type preferences (only show user-configurable types)
const groupedTypes = computed(() => {
  const groups: Record<string, NotificationType[]> = {}
  for (const type of types.value) {
    if (!type.is_user_configurable) continue
    if (!groups[type.category]) groups[type.category] = []
    groups[type.category].push(type)
  }
  return groups
})

function getPreference(typeId: string) {
  return preferences.value.get(typeId) || { email: true, push: true, telegram: false }
}

// Auto-save
const autoSaveStatus = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')
let savedResetTimer: ReturnType<typeof setTimeout> | null = null

async function doSavePreferences() {
  autoSaveStatus.value = 'saving'
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
    autoSaveStatus.value = 'saved'
    if (savedResetTimer) clearTimeout(savedResetTimer)
    savedResetTimer = setTimeout(() => { autoSaveStatus.value = 'idle' }, 2500)
  } catch {
    autoSaveStatus.value = 'error'
    toast.error(t('notifications.preferences.saveFailed'))
  }
}

const debouncedSave = useDebounceFn(doSavePreferences, 800)

function setPreference(typeId: string, channel: 'email' | 'push' | 'telegram', value: boolean) {
  const current = getPreference(typeId)
  preferences.value.set(typeId, { ...current, [channel]: value })
  autoSaveStatus.value = 'saving'
  debouncedSave()
}

// Default reminders
const defaultReminderEntries = ref<ReminderOffsetEntry[]>([])

// Lifecycle
onMounted(async () => {
  try {
    const [typesData, prefsData] = await Promise.all([
      notificationStore.fetchNotificationTypes(),
      notificationStore.fetchPreferences(),
      notificationStore.fetchTelegramBinding(),
      notificationStore.fetchTelegramConfig(),
      notificationStore.fetchGlobalChannelSettings(),
      reminderStore.fetchDefaultOffsets().then((entries) => {
        defaultReminderEntries.value = entries
      }),
    ])

    types.value = typesData

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
      <h1 data-testid="page-heading" class="text-3xl font-bold tracking-tight break-words">
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
      <!-- ── Delivery Channels ─────────────────────────────────── -->
      <h2 class="text-xl font-semibold tracking-tight">
        {{ t('notifications.channels.sectionTitle') }}
      </h2>

      <!-- Email channel -->
      <Card
        data-testid="channel-email"
        :class="[
          'transition-colors duration-300',
          globalChannelSettings.notify_email
            ? 'border-blue-200 bg-blue-50/50 dark:border-blue-900 dark:bg-blue-950/20'
            : '',
        ]"
      >
        <CardHeader>
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <AnimatedMail
                ref="mailIconRef"
                :size="20"
                :class="[
                  'transition-colors duration-300',
                  globalChannelSettings.notify_email ? 'text-blue-600 dark:text-blue-400' : 'text-muted-foreground',
                ]"
              />
              <CardTitle>{{ t('notifications.email.title') }}</CardTitle>
            </div>
            <Switch
              :model-value="globalChannelSettings.notify_email"
              @update:model-value="(v: boolean) => toggleGlobalChannel('notify_email', v)"
            />
          </div>
          <CardDescription>
            {{ t('notifications.email.description') }}
          </CardDescription>
        </CardHeader>
      </Card>

      <!-- Push channel -->
      <PushChannelCard
        data-testid="channel-push"
        :enabled="globalChannelSettings.notify_push"
        @toggle="(v) => toggleGlobalChannel('notify_push', v)"
      />

      <!-- Telegram channel -->
      <TelegramChannelCard
        data-testid="channel-telegram"
        :enabled="globalChannelSettings.notify_telegram"
        @toggle="(v) => toggleGlobalChannel('notify_telegram', v)"
      />

      <!-- ── Default Booking Reminders ────────────────────────── -->
      <h2 class="text-xl font-semibold tracking-tight pt-4">
        {{ t('notifications.reminders.title') }}
      </h2>

      <DefaultRemindersCard
        data-testid="section-reminders"
        :entries="defaultReminderEntries"
        :available-channels="reminderChannels"
        @update:entries="defaultReminderEntries = $event"
      />

      <!-- ── Per-type Preferences ──────────────────────────────── -->
      <h2 class="text-xl font-semibold tracking-tight pt-4">
        {{ t('notifications.preferences.perTypeTitle') }}
      </h2>

      <PerTypePreferencesSection
        data-testid="section-per-type"
        :grouped-types="groupedTypes"
        :preferences="preferences"
        @set-preference="setPreference"
      />
    </template>

    <!-- Fixed auto-save indicator -->
    <Transition
      enter-active-class="transition-all duration-300 ease-out"
      leave-active-class="transition-all duration-300 ease-in"
      enter-from-class="opacity-0 translate-y-4"
      leave-to-class="opacity-0 translate-y-4"
    >
      <div
        v-if="autoSaveStatus === 'saving' || autoSaveStatus === 'saved'"
        class="fixed bottom-6 left-1/2 z-50 -translate-x-1/2"
      >
        <div
          :class="[
            'flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium shadow-lg',
            autoSaveStatus === 'saving'
              ? 'bg-muted text-muted-foreground'
              : 'bg-green-100 text-green-700 dark:bg-green-900/60 dark:text-green-300',
          ]"
        >
          <LoaderCircle v-if="autoSaveStatus === 'saving'" class="h-4 w-4 animate-spin" />
          <Check v-else class="h-4 w-4" />
          {{
            autoSaveStatus === 'saving'
              ? t('notifications.preferences.autoSaving')
              : t('notifications.preferences.autoSaved')
          }}
        </div>
      </div>
    </Transition>
  </div>
</template>
