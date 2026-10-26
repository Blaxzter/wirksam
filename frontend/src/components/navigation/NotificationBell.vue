<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import { Bell, CheckCheck, Settings, Trash2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'

import { useDialog } from '@/composables/useDialog'

import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Separator } from '@/components/ui/separator'

import NotificationList from '@/components/navigation/NotificationList.vue'
import HintTooltip from '@/components/utils/HintTooltip.vue'

const { t } = useI18n()
const router = useRouter()
const notificationStore = useNotificationStore()
const authStore = useAuthStore()
const { confirmDestructive } = useDialog()

const popoverOpen = ref(false)

const unreadCount = computed(() => notificationStore.unreadCount)

// A new notification may be a team request to decide. The stream only sends
// the count, so re-read the selected event: its `pending_team_request_count`
// drives the Teams badge in the sidebar and the More sheet, which should keep
// up the way this bell does.
watch(unreadCount, (now, before) => {
  if (now > before && authStore.selectedEventId) {
    void authStore.refreshSelectedEvent(authStore.selectedEventId)
  }
})
const hasUnread = computed(() => notificationStore.hasUnread)
const hasAny = computed(() => notificationStore.notifications.length > 0)

const displayCount = computed(() => {
  if (unreadCount.value > 99) return '99+'
  return unreadCount.value.toString()
})

async function onOpen(open: boolean) {
  if (open) {
    await notificationStore.fetchNotifications({ limit: 20 })
  }
}

async function handleMarkAllAsRead() {
  await notificationStore.markAllAsRead()
}

async function handleDismissAll() {
  popoverOpen.value = false
  const confirmed = await confirmDestructive({
    title: t('notifications.deleteAllTitle'),
    text: t('notifications.deleteAllConfirm'),
  })
  if (!confirmed) return
  try {
    await notificationStore.dismissAllNotifications()
    toast.success(t('notifications.deletedAll'))
  } catch {
    toast.error(t('notifications.deleteAllFailed'))
  }
}

function goToPreferences() {
  popoverOpen.value = false
  router.push({ name: 'notification-preferences' })
}

function goToNotifications() {
  popoverOpen.value = false
  router.push({ name: 'notifications' })
}

onMounted(() => {
  notificationStore.startStream()
})

onUnmounted(() => {
  notificationStore.stopStream()
})
</script>

<template>
  <Popover v-model:open="popoverOpen" @update:open="onOpen">
    <PopoverTrigger as-child>
      <Button
        variant="ghost"
        size="icon"
        class="relative"
        data-testid="notification-bell"
        :aria-label="t('notifications.openNotifications')"
      >
        <Bell class="h-5 w-5" />
        <span
          v-if="hasUnread"
          class="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-700 px-0.5 text-[10px] font-bold text-white"
        >
          {{ displayCount }}
        </span>
      </Button>
    </PopoverTrigger>

    <PopoverContent class="w-96 p-0" align="end" :side-offset="8">
      <!-- Header -->
      <div class="flex items-center justify-between border-b px-4 py-3">
        <h3 class="text-sm font-semibold">
          {{ t('notifications.title') }}
        </h3>
        <div class="flex items-center gap-1">
          <Button
            v-if="hasUnread"
            variant="ghost"
            size="sm"
            class="h-7 text-xs"
            @click="handleMarkAllAsRead"
          >
            <CheckCheck class="mr-1 h-3 w-3" />
            {{ t('notifications.markAllRead') }}
          </Button>
          <HintTooltip v-if="hasAny" :label="t('notifications.deleteAll')">
            <Button
              variant="ghost"
              size="icon"
              class="h-7 w-7 hover:text-red-700 dark:hover:text-red-400"
              :aria-label="t('notifications.deleteAll')"
              @click="handleDismissAll"
            >
              <Trash2 class="h-3.5 w-3.5" />
            </Button>
          </HintTooltip>
          <HintTooltip :label="t('notifications.managePreferences')">
            <Button
              variant="ghost"
              size="icon"
              class="h-7 w-7"
              :aria-label="t('notifications.managePreferences')"
              @click="goToPreferences"
            >
              <Settings class="h-3.5 w-3.5" />
            </Button>
          </HintTooltip>
        </div>
      </div>

      <!-- Notification list -->
      <div class="max-h-96 overflow-y-auto">
        <NotificationList @navigate="popoverOpen = false" />
      </div>

      <!-- Footer -->
      <Separator />
      <div class="flex items-center justify-between gap-2 p-2">
        <Button variant="ghost" size="sm" class="text-xs" @click="goToNotifications">
          {{ t('notifications.viewAll') }}
        </Button>
        <Button variant="ghost" size="sm" class="text-xs" @click="goToPreferences">
          {{ t('notifications.managePreferences') }}
        </Button>
      </div>
    </PopoverContent>
  </Popover>
</template>
