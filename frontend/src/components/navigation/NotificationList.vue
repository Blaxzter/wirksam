<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { Bell, Loader2 } from '@lucide/vue'
import { useNow } from '@vueuse/core'
import { useI18n } from 'vue-i18n'

import { type NotificationItem, useNotificationStore } from '@/stores/notification'

import { Skeleton } from '@/components/ui/skeleton'

import NotificationRow from '@/components/notifications/NotificationRow.vue'

import { groupByDay, notificationTarget } from '@/lib/notifications'

/**
 * The bell's dropdown: the newest notices as small cards under "Today",
 * "Yesterday" and "Earlier", the same rows the inbox page shows. Clicking one
 * marks it read and opens what it is about (`navigate` closes the dropdown).
 */
const emit = defineEmits<{
  navigate: []
}>()

const { t } = useI18n()
const notificationStore = useNotificationStore()

const notifications = computed(() => notificationStore.notifications)
const hasMore = computed(() => notificationStore.hasMore)
const loading = computed(() => notificationStore.loading)

/** One clock for the whole list, so "5 min ago" moves on while it is open. */
const now = useNow({ interval: 60_000 })
const groups = computed(() => groupByDay(notifications.value, now.value))

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

function open(notification: NotificationItem) {
  if (!notification.is_read) notificationStore.markAsRead(notification.id)
  // The row is a link; the dropdown only has to get out of the way.
  if (notificationTarget(notification.data)) emit('navigate')
}
</script>

<template>
  <div>
    <!-- Initial load skeletons -->
    <div
      v-if="loading && notifications.length === 0"
      aria-busy="true"
      :aria-label="t('notifications.title')"
      class="space-y-2 p-3"
    >
      <div v-for="i in 3" :key="i" class="flex gap-2.5 rounded-2xl border p-3">
        <Skeleton class="size-9 shrink-0 rounded-[10px]" />
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

    <div v-else class="px-3 pt-1 pb-3">
      <section
        v-for="group in groups"
        :key="group.key"
        :aria-labelledby="`bell-group-${group.key}`"
      >
        <h4
          :id="`bell-group-${group.key}`"
          class="text-muted-foreground px-1 pt-3 pb-2 text-xs font-bold tracking-wide uppercase"
        >
          {{ t(`notifications.groups.${group.key}`) }}
        </h4>
        <ul class="space-y-2">
          <li v-for="notification in group.items" :key="notification.id">
            <NotificationRow
              :notification="notification"
              :now="now"
              dense
              @open="open(notification)"
              @read="notificationStore.markAsRead(notification.id)"
              @dismiss="notificationStore.dismissNotification(notification.id)"
            />
          </li>
        </ul>
      </section>
    </div>

    <div v-if="hasMore" ref="sentinel" class="flex justify-center py-3">
      <Loader2 class="text-muted-foreground h-4 w-4 animate-spin" />
    </div>

    <div
      v-if="!hasMore && notifications.length > 0"
      class="text-muted-foreground pb-3 text-center text-xs"
    >
      {{ t('notifications.allLoaded') }}
    </div>
  </div>
</template>
