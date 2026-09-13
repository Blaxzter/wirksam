<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { Bell, Check, Loader2, Trash2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { useNotificationStore } from '@/stores/notification'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

const emit = defineEmits<{
  navigate: []
}>()

const { t } = useI18n()
const router = useRouter()
const notificationStore = useNotificationStore()

const notifications = computed(() => notificationStore.notifications)
const hasMore = computed(() => notificationStore.hasMore)
const loading = computed(() => notificationStore.loading)

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

async function handleMarkAsRead(id: string) {
  await notificationStore.markAsRead(id)
}

async function handleDismiss(id: string) {
  await notificationStore.dismissNotification(id)
}

function handleNotificationClick(notification: (typeof notifications.value)[0]) {
  if (!notification.is_read) {
    notificationStore.markAsRead(notification.id)
  }

  const data = notification.data
  if (data) {
    if (data.task_id) {
      emit('navigate')
      router.push({ name: 'task-detail', params: { eventId: data.task_id as string } })
    } else if (data.event_id) {
      emit('navigate')
      router.push({
        name: 'event-settings',
        params: { eventId: data.event_id as string },
      })
    } else if (data.booking_id) {
      emit('navigate')
      router.push({ name: 'my-bookings' })
    }
  }
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
    'shift.time_changed': '🕐',
    'task.published': '📅',
    'event.cloned': '📑',
    'event.published': '📋',
    'user.registered': '👤',
    'user.approved': '✓',
    'user.rejected': '✕',
  }
  return iconMap[typeCode] || '📌'
}
</script>

<template>
  <div>
    <!-- Initial load skeletons -->
    <div
      v-if="loading && notifications.length === 0"
      aria-busy="true"
      :aria-label="t('notifications.title')"
    >
      <div
        v-for="i in 3"
        :key="i"
        class="flex gap-3 px-4 py-3"
      >
        <Skeleton class="mt-0.5 h-5 w-5 rounded-full" />
        <div class="min-w-0 flex-1">
          <Skeleton class="mb-1.5 h-4 w-2/3" />
          <Skeleton class="mb-1.5 h-3 w-full" />
          <Skeleton class="h-2.5 w-12" />
        </div>
      </div>
    </div>

    <div v-else-if="notifications.length === 0" class="px-4 py-8 text-center">
      <Bell class="text-muted-foreground mx-auto mb-2 h-8 w-8" />
      <p class="text-muted-foreground text-sm">
        {{ t('notifications.empty') }}
      </p>
    </div>

    <div
      v-for="notification in notifications"
      :key="notification.id"
      class="event hover:bg-muted/50 flex cursor-pointer gap-3 px-4 py-3 transition-colors"
      :class="{ 'bg-muted/30': !notification.is_read }"
      @click="handleNotificationClick(notification)"
    >
      <div class="flex-shrink-0 pt-0.5 text-lg">
        {{ getNotificationIcon(notification.notification_type_code) }}
      </div>

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

      <div class="flex flex-shrink-0 items-start pt-1">
        <span v-if="!notification.is_read" class="bg-primary h-2 w-2 rounded-full" />
        <span v-else class="h-2 w-2" />
      </div>

      <div class="hidden flex-shrink-0 flex-col gap-1 event-hover:flex">
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

    <div v-if="hasMore" ref="sentinel" class="flex justify-center py-3">
      <Loader2 class="text-muted-foreground h-4 w-4 animate-spin" />
    </div>

    <div
      v-if="!hasMore && notifications.length > 0"
      class="text-muted-foreground py-3 text-center text-xs"
    >
      {{ t('notifications.allLoaded') }}
    </div>
  </div>
</template>
