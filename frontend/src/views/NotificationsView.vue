<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import { Bell, CheckCheck, ExternalLink, Loader2, Settings, Trash2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import {
  NOTIFICATION_CLASSIFICATIONS,
  type NotificationClassification,
  type NotificationItem,
  useNotificationStore,
} from '@/stores/notification'

import { useDialog } from '@/composables/useDialog'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

import HintTooltip from '@/components/utils/HintTooltip.vue'

const { t } = useI18n()
const router = useRouter()
const notificationStore = useNotificationStore()
const { confirmDestructive } = useDialog()

type Filter = NotificationClassification | 'all'

const activeFilter = ref<Filter>('all')

const notifications = computed<NotificationItem[]>(() => notificationStore.notifications)
const hasUnread = computed(() => notificationStore.hasUnread)
const hasAny = computed(() => notifications.value.length > 0)
const hasMore = computed(() => notificationStore.hasMore)
const loading = computed(() => notificationStore.loading)
const initialLoading = computed(() => loading.value && notifications.value.length === 0)

const countsByClassification = computed(() => {
  const counts: Record<NotificationClassification, number> = {
    reminder: 0,
    change: 0,
    match: 0,
    announcement: 0,
  }
  for (const n of notifications.value) counts[n.classification] += 1
  return counts
})

const filtered = computed<NotificationItem[]>(() => {
  if (activeFilter.value === 'all') return notifications.value
  return notifications.value.filter((n) => n.classification === activeFilter.value)
})

const filterPills = computed<{ key: Filter; label: string; count: number }[]>(() => [
  {
    key: 'all',
    label: t('notifications.classifications.all'),
    count: notifications.value.length,
  },
  ...NOTIFICATION_CLASSIFICATIONS.map((c) => ({
    key: c,
    label: t(`notifications.classifications.${pluralKey(c)}`),
    count: countsByClassification.value[c],
  })),
])

function pluralKey(c: NotificationClassification): string {
  return (
    {
      reminder: 'reminders',
      change: 'changes',
      match: 'matches',
      announcement: 'announcements',
    } as const
  )[c]
}

const TONE_BY_CLASSIFICATION: Record<NotificationClassification, { bg: string; fg: string }> = {
  reminder: { bg: 'bg-[#D9E4EC]', fg: 'text-[#4E7A95]' },
  change: { bg: 'bg-[#F7EAC8]', fg: 'text-[#8C6418]' },
  match: { bg: 'bg-[#E3EDE3]', fg: 'text-[#2F5D3A]' },
  announcement: { bg: 'bg-[#F5E1D3]', fg: 'text-[#C96A3C]' },
}

function classificationLabel(c: NotificationClassification): string {
  return t(`notifications.classifications.${c}`)
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

async function handleMarkAllAsRead() {
  await notificationStore.markAllAsRead()
}

async function handleDismissAll() {
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

async function handleMarkAsRead(id: string) {
  await notificationStore.markAsRead(id)
}

async function handleDismiss(id: string) {
  await notificationStore.dismissNotification(id)
}

function routeFor(n: NotificationItem) {
  const data = n.data
  if (!data) return null
  if (data.task_id) return { name: 'task-detail', params: { eventId: data.task_id as string } }
  // Team requests and decisions open the Teams page on that team.
  if (data.team_id && data.event_id)
    return {
      name: 'teams',
      params: { eventId: data.event_id as string },
      query: { team: data.team_id as string },
    }
  if (data.event_id) return { name: 'event-settings', params: { eventId: data.event_id as string } }
  if (data.booking_id) return { name: 'my-bookings' }
  return null
}

// ── Click → expand inline action row ─────────────────────────────
const expandedId = ref<string | null>(null)

function handleClick(n: NotificationItem) {
  if (!n.is_read) notificationStore.markAsRead(n.id)
  if (!routeFor(n)) {
    expandedId.value = null
    return
  }
  expandedId.value = expandedId.value === n.id ? null : n.id
}

function openTarget(n: NotificationItem) {
  const route = routeFor(n)
  if (!route) return
  expandedId.value = null
  router.push(route)
}

function goToPreferences() {
  router.push({ name: 'notification-preferences' })
}

async function loadMore() {
  if (!hasMore.value || loading.value) return
  await notificationStore.loadMoreNotifications()
}

// ── Pills horizontal-scroll fade gradients ────────────────────────
const pillsContainer = ref<HTMLElement | null>(null)
const showFadeLeft = ref(false)
const showFadeRight = ref(false)
const FADE_THRESHOLD = 2

function updatePillsOverflow() {
  const el = pillsContainer.value
  if (!el) return
  showFadeLeft.value = el.scrollLeft > FADE_THRESHOLD
  showFadeRight.value = el.scrollWidth - el.scrollLeft - el.clientWidth > FADE_THRESHOLD
}

watch(filterPills, () => nextTick(updatePillsOverflow))

// ── Swipe gestures ───────────────────────────────────────────────
// Single active swipe at a time. Right-swipe → mark read; left-swipe → dismiss.
const SWIPE_TRIGGER_PX = 80
const SWIPE_MOVE_THRESHOLD_PX = 8

const swipingId = ref<string | null>(null)
const swipeOffset = ref(0)
const swipeAnimating = ref(false)
let swipeStartX = 0
let swipeStartY = 0
let swipeAxisLocked: 'x' | 'y' | null = null
// True once we've crossed the move threshold, so the row's click can be
// suppressed even after the pointer is released.
let swipeWasDrag = false

function rowTransform(id: string) {
  if (swipingId.value !== id) return undefined
  return {
    transform: `translateX(${swipeOffset.value}px)`,
    transition: swipeAnimating.value ? 'transform 180ms ease-out' : 'none',
  }
}

function onPointerDown(n: NotificationItem, e: PointerEvent) {
  // Only react to touch / pen — desktop mouse uses click + hover.
  if (e.pointerType === 'mouse') return
  // Don't treat taps on the action panel as the start of a swipe.
  if ((e.target as HTMLElement).closest('[data-no-swipe]')) return
  swipingId.value = n.id
  swipeStartX = e.clientX
  swipeStartY = e.clientY
  swipeOffset.value = 0
  swipeAxisLocked = null
  swipeAnimating.value = false
  swipeWasDrag = false
}

function onPointerMove(n: NotificationItem, e: PointerEvent) {
  if (swipingId.value !== n.id) return
  const dx = e.clientX - swipeStartX
  const dy = e.clientY - swipeStartY
  if (swipeAxisLocked == null) {
    if (Math.abs(dx) < SWIPE_MOVE_THRESHOLD_PX && Math.abs(dy) < SWIPE_MOVE_THRESHOLD_PX) return
    swipeAxisLocked = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y'
  }
  if (swipeAxisLocked !== 'x') return
  swipeWasDrag = true
  // Right-swipe only makes sense for unread items (nothing to mark on read ones).
  let clamped = dx
  if (n.is_read && dx > 0) clamped = 0
  swipeOffset.value = clamped
}

function resetSwipe() {
  swipeAnimating.value = true
  swipeOffset.value = 0
  setTimeout(() => {
    if (swipeOffset.value === 0) {
      swipingId.value = null
      swipeAnimating.value = false
    }
  }, 200)
}

async function onPointerUp(n: NotificationItem) {
  if (swipingId.value !== n.id) return
  const dx = swipeOffset.value
  if (dx <= -SWIPE_TRIGGER_PX) {
    // Animate off-screen then dismiss.
    swipeAnimating.value = true
    swipeOffset.value = -window.innerWidth
    setTimeout(() => {
      swipingId.value = null
      void handleDismiss(n.id)
    }, 180)
    return
  }
  if (dx >= SWIPE_TRIGGER_PX && !n.is_read) {
    void handleMarkAsRead(n.id)
  }
  resetSwipe()
}

function onRowClickCapture(e: MouseEvent) {
  if (swipeWasDrag) {
    e.stopPropagation()
    e.preventDefault()
    swipeWasDrag = false
  }
}

onMounted(() => {
  notificationStore.fetchNotifications({ limit: 20 })
  nextTick(updatePillsOverflow)
})
</script>

<template>
  <div class="mx-auto max-w-2xl space-y-5">
    <!-- Header -->
    <div class="flex flex-wrap items-baseline justify-between gap-3">
      <h1 data-testid="page-heading" class="text-2xl sm:text-3xl font-bold tracking-tight">
        {{ t('notifications.title') }}
      </h1>
      <div class="flex items-center gap-1">
        <button
          v-if="hasUnread"
          type="button"
          class="text-primary hover:text-primary/80 cursor-pointer text-xs font-semibold tracking-wide transition-colors"
          @click="handleMarkAllAsRead"
        >
          {{ t('notifications.markAllRead') }}
        </button>
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

    <!-- Classification pills (horizontal scroll, no wrap) -->
    <div class="relative overflow-hidden">
      <div
        class="from-background pointer-events-none absolute inset-y-0 left-0 z-10 w-6 bg-gradient-to-r to-transparent transition-opacity duration-200"
        :class="showFadeLeft ? 'opacity-100' : 'opacity-0'"
      />
      <div
        class="from-background pointer-events-none absolute inset-y-0 right-0 z-10 w-6 bg-gradient-to-l to-transparent transition-opacity duration-200"
        :class="showFadeRight ? 'opacity-100' : 'opacity-0'"
      />
      <div
        ref="pillsContainer"
        role="tablist"
        class="no-scrollbar touch-pan-x flex gap-1.5 overflow-x-auto scroll-smooth"
        @scroll="updatePillsOverflow"
      >
        <button
          v-for="pill in filterPills"
          :key="pill.key"
          type="button"
          role="tab"
          :aria-selected="activeFilter === pill.key"
          class="inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium whitespace-nowrap transition-colors"
          :class="
            activeFilter === pill.key
              ? 'bg-foreground text-background'
              : 'bg-card text-muted-foreground border-border hover:bg-muted border'
          "
          @click="activeFilter = pill.key"
        >
          {{ pill.label }}
          <span
            v-if="pill.count > 0"
            class="rounded-full px-1.5 py-px text-[10px] leading-tight font-semibold"
            :class="
              activeFilter === pill.key
                ? 'bg-background/20 text-background'
                : 'bg-muted text-foreground'
            "
          >
            {{ pill.count }}
          </span>
        </button>
      </div>
    </div>

    <!-- Initial load: skeleton rows mirroring real entries. -->
    <ul
      v-if="initialLoading"
      aria-busy="true"
      :aria-label="t('notifications.title')"
      class="divide-border divide-y sm:divide-y-0 sm:divide-transparent sm:space-y-2"
    >
      <li
        v-for="i in 3"
        :key="i"
        class="bg-background relative flex gap-3 py-3.5 pr-4 pl-6 sm:bg-card sm:border-border sm:rounded-lg sm:border sm:px-5 sm:py-4 sm:pl-7"
      >
        <div class="min-w-0 flex-1 pr-20">
          <div class="mb-2 flex items-center gap-2">
            <Skeleton class="h-4 w-16 rounded-full" />
            <Skeleton class="h-3 w-12" />
          </div>
          <Skeleton class="mb-1.5 h-4 w-2/3" />
          <Skeleton class="h-3 w-5/6" />
        </div>
      </li>
    </ul>

    <!-- Empty state -->
    <div
      v-else-if="filtered.length === 0"
      class="bg-card border-border rounded-lg border px-4 py-12 text-center"
    >
      <Bell class="text-muted-foreground mx-auto mb-2 h-8 w-8" />
      <p class="text-muted-foreground text-sm">{{ t('notifications.empty') }}</p>
    </div>

    <!-- Mobile: flat list with row dividers, no card chrome.
         Desktop (sm+): each entry becomes its own card with spacing. -->
    <ul v-else class="divide-border divide-y sm:divide-y-0 sm:divide-transparent sm:space-y-2">
      <li
        v-for="n in filtered"
        :key="n.id"
        data-testid="notification-row"
        class="relative overflow-hidden sm:overflow-visible"
      >
        <!-- Swipe action backgrounds (revealed under the row) -->
        <div
          v-if="swipingId === n.id"
          class="pointer-events-none absolute inset-0 flex items-center justify-between px-5 sm:hidden"
          :class="
            swipeOffset > 0
              ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300'
              : swipeOffset < 0
                ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
                : ''
          "
        >
          <CheckCheck v-if="swipeOffset > 0" class="h-5 w-5" />
          <span v-else />
          <Trash2 v-if="swipeOffset < 0" class="h-5 w-5" />
          <span v-else />
        </div>

        <div
          class="bg-background relative flex cursor-pointer touch-pan-y gap-3 py-3.5 pr-4 pl-6 transition-colors hover:bg-black/[0.025] sm:bg-card sm:border-border sm:rounded-lg sm:border sm:px-5 sm:py-4 sm:pl-7 sm:hover:bg-card/80"
          :style="rowTransform(n.id)"
          @click="handleClick(n)"
          @click.capture="onRowClickCapture($event)"
          @pointerdown="onPointerDown(n, $event)"
          @pointermove="onPointerMove(n, $event)"
          @pointerup="onPointerUp(n)"
          @pointercancel="resetSwipe"
        >
          <span
            v-if="!n.is_read"
            aria-hidden="true"
            class="absolute top-4.5 left-2 h-2 w-2 rounded-full bg-[#C96A3C] sm:left-2.5"
          />

          <div class="min-w-0 flex-1 pr-20">
            <div class="mb-1 flex items-center gap-2">
              <span
                class="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium"
                :class="[
                  TONE_BY_CLASSIFICATION[n.classification].bg,
                  TONE_BY_CLASSIFICATION[n.classification].fg,
                ]"
              >
                {{ classificationLabel(n.classification) }}
              </span>
              <span class="text-muted-foreground text-[11px]">{{
                formatTimeAgo(n.created_at)
              }}</span>
            </div>
            <p
              class="text-sm leading-snug tracking-tight"
              :class="n.is_read ? 'font-medium' : 'font-semibold'"
            >
              {{ n.title }}
            </p>
            <p class="text-muted-foreground mt-0.5 text-xs leading-snug">
              {{ n.body }}
            </p>

            <!-- Inline action row, expands when the user clicks an item that
                 has a navigable target. Replaces the previous full-screen sheet. -->
            <Transition
              enter-active-class="transition-all duration-150 ease-out"
              enter-from-class="-translate-y-1 opacity-0"
              enter-to-class="translate-y-0 opacity-100"
              leave-active-class="transition-all duration-100 ease-in"
              leave-from-class="opacity-100"
              leave-to-class="opacity-0"
            >
              <div v-if="expandedId === n.id && routeFor(n)" class="mt-3 flex gap-2">
                <Button size="sm" @click.stop="openTarget(n)">
                  <ExternalLink class="mr-1.5 h-3.5 w-3.5" />
                  {{ t('notifications.detail.open') }}
                </Button>
                <Button variant="ghost" size="sm" @click.stop="expandedId = null">
                  {{ t('notifications.detail.close') }}
                </Button>
              </div>
            </Transition>
          </div>

          <!-- Always-visible quick actions (mark read + dismiss) -->
          <div
            data-no-swipe
            class="bg-background border-border absolute top-2 right-2 flex gap-1 rounded-md border p-0.5 shadow-sm"
          >
            <HintTooltip v-if="!n.is_read" :label="t('notifications.markRead')">
              <Button
                variant="ghost"
                size="icon"
                class="h-7 w-7 cursor-pointer hover:bg-green-100 hover:text-green-700 dark:hover:bg-green-900/30 dark:hover:text-green-400"
                :aria-label="t('notifications.markRead')"
                @click.stop="handleMarkAsRead(n.id)"
              >
                <CheckCheck class="h-3.5 w-3.5" />
              </Button>
            </HintTooltip>
            <HintTooltip :label="t('notifications.dismiss')">
              <Button
                variant="ghost"
                size="icon"
                class="h-7 w-7 cursor-pointer hover:bg-red-100 hover:text-red-700 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                :aria-label="t('notifications.dismiss')"
                @click.stop="handleDismiss(n.id)"
              >
                <Trash2 class="h-3.5 w-3.5" />
              </Button>
            </HintTooltip>
          </div>
        </div>
      </li>
    </ul>

    <div v-if="hasMore" class="flex justify-center pt-1">
      <Button variant="ghost" size="sm" :disabled="loading" @click="loadMore">
        <Loader2 v-if="loading" class="text-muted-foreground mr-1 h-3 w-3 animate-spin" />
        {{ t('notifications.viewAll') }}
      </Button>
    </div>

    <div
      v-else-if="notifications.length > 0"
      class="text-muted-foreground pt-1 text-center text-xs"
    >
      {{ t('notifications.allLoaded') }}
    </div>
  </div>
</template>

<style scoped>
.no-scrollbar {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
.no-scrollbar::-webkit-scrollbar {
  display: none;
}
</style>
