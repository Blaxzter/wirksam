<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import { Bell, Check, CheckCheck, Loader2, Settings, Trash2 } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { useNotificationStore } from '@/stores/notification'

import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Separator } from '@/components/ui/separator'

const { t } = useI18n()
const router = useRouter()
const notificationStore = useNotificationStore()

const popoverOpen = ref(false)

const unreadCount = computed(() => notificationStore.unreadCount)
const hasUnread = computed(() => notificationStore.hasUnread)
const notifications = computed(() => notificationStore.notifications)
const hasMore = computed(() => notificationStore.hasMore)
const loading = computed(() => notificationStore.loading)

const displayCount = computed(() => {
  if (unreadCount.value > 99) return '99+'
  return unreadCount.value.toString()
})

const sentinel = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

watch(sentinel, (el) => {
  observer?.disconnect()
  observer = null
  if (el) {
    observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          notificationStore.loadMoreNotifications()
        }
      },
      { threshold: 0.1 },
    )
    observer.observe(el)
  }
})

async function onOpen(open: boolean) {
  if (open) {
    await notificationStore.fetchNotifications({ limit: 20 })
  }
}

async function handleMarkAsRead(id: string) {
  await notificationStore.markAsRead(id)
}

async function handleMarkAllAsRead() {
  await notificationStore.markAllAsRead()
}

async function handleDismiss(id: string) {
  await notificationStore.dismissNotification(id)
}

function handleNotificationClick(notification: (typeof notifications.value)[0]) {
  if (!notification.is_read) {
    notificationStore.markAsRead(notification.id)
  }

  // Navigate based on notification data
  const data = notification.data
  if (data) {
    if (data.event_id) {
      popoverOpen.value = false
      router.push({ name: 'event-detail', params: { eventId: data.event_id as string } })
    } else if (data.event_group_id) {
      popoverOpen.value = false
      router.push({
        name: 'event-group-detail',
        params: { groupId: data.event_group_id as string },
      })
    } else if (data.booking_id) {
      popoverOpen.value = false
      router.push({ name: 'my-bookings' })
    }
  }
}

function goToPreferences() {
  popoverOpen.value = false
  router.push({ name: 'notification-preferences' })
}

function formatTimeAgo(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMin / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMin < 1) return t('notifications.timeAgo.justNow')
  if (diffMin < 60) return t('notifications.timeAgo.minutes', { n: diffMin })
  if (diffHours < 24) return t('notifications.timeAgo.hours', { n: diffHours })
  if (diffDays < 7) return t('notifications.timeAgo.days', { n: diffDays })
  return date.toLocaleDateString()
}

function getNotificationIcon(typeCode: string): string {
  const iconMap: Record<string, string> = {
    'booking.confirmed': '✓',
    'booking.cancelled_by_user': '✕',
    'booking.cancelled_by_admin': '⚠',
    'booking.slot_cobooked': '👥',
    'slot.time_changed': '🕐',
    'event.published': '📅',
    'event_group.published': '📋',
    'user.registered': '👤',
    'user.approved': '✓',
    'user.rejected': '✕',
  }
  return iconMap[typeCode] || '📌'
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
      <Button variant="ghost" size="icon" class="relative" data-testid="notification-bell">
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
          <Button variant="ghost" size="icon" class="h-7 w-7" @click="goToPreferences">
            <Settings class="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <!-- Notification list -->
      <div class="max-h-96 overflow-y-auto">
        <div v-if="notifications.length === 0 && !loading" class="px-4 py-8 text-center">
          <Bell class="text-muted-foreground mx-auto mb-2 h-8 w-8" />
          <p class="text-muted-foreground text-sm">
            {{ t('notifications.empty') }}
          </p>
        </div>

        <div
          v-for="notification in notifications"
          :key="notification.id"
          class="group hover:bg-muted/50 flex cursor-pointer gap-3 px-4 py-3 transition-colors"
          :class="{ 'bg-muted/30': !notification.is_read }"
          @click="handleNotificationClick(notification)"
        >
          <!-- Icon -->
          <div class="flex-shrink-0 pt-0.5 text-lg">
            {{ getNotificationIcon(notification.notification_type_code) }}
          </div>

          <!-- Content -->
          <div class="min-w-0 flex-1">
            <p class="truncate text-sm font-medium" :class="{ 'font-bold': !notification.is_read }">
              {{ notification.title }}
            </p>
            <p class="text-muted-foreground mt-0.5 line-clamp-2 text-xs">
              {{ notification.body }}
            </p>
            <p class="text-muted-foreground mt-1 text-[10px]">
              {{ formatTimeAgo(notification.created_at) }}
            </p>
          </div>

          <!-- Unread dot -->
          <div class="flex flex-shrink-0 items-start pt-1">
            <span v-if="!notification.is_read" class="bg-primary h-2 w-2 rounded-full" />
            <span v-else class="h-2 w-2" />
          </div>

          <!-- Actions (hidden until hover, appear to the right of dot) -->
          <div class="hidden flex-shrink-0 flex-col gap-1 group-hover:flex">
            <Button
              v-if="!notification.is_read"
              variant="ghost"
              size="icon"
              class="h-6 w-6 cursor-pointer hover:bg-green-100 hover:text-green-700 dark:hover:bg-green-900/30 dark:hover:text-green-400"
              :title="t('notifications.markRead')"
              @click.stop="handleMarkAsRead(notification.id)"
            >
              <Check class="h-3 w-3" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              class="h-6 w-6 cursor-pointer hover:bg-red-100 hover:text-red-700 dark:hover:bg-red-900/30 dark:hover:text-red-400"
              :title="t('notifications.dismiss')"
              @click.stop="handleDismiss(notification.id)"
            >
              <Trash2 class="h-3 w-3" />
            </Button>
          </div>
        </div>

        <!-- Infinite scroll sentinel / loader -->
        <div v-if="hasMore" ref="sentinel" class="flex justify-center py-3">
          <Loader2 class="text-muted-foreground h-4 w-4 animate-spin" />
        </div>

        <!-- End of list -->
        <div
          v-if="!hasMore && notifications.length > 0"
          class="text-muted-foreground py-3 text-center text-xs"
        >
          {{ t('notifications.allLoaded') }}
        </div>
      </div>

      <!-- Footer -->
      <Separator />
      <div class="p-2 text-center">
        <Button variant="ghost" size="sm" class="text-xs" @click="goToPreferences">
          {{ t('notifications.managePreferences') }}
        </Button>
      </div>
    </PopoverContent>
  </Popover>
</template>
