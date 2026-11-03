<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import { Bell, CheckCheck, Ellipsis, Loader2, Settings, Trash2 } from '@lucide/vue'
import { useNow } from '@vueuse/core'
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'

import NotificationRow from '@/components/notifications/NotificationRow.vue'

import { groupByDay } from '@/lib/notifications'

/**
 * The inbox: every notice as a card, newest first, under "Today",
 * "Yesterday" and "Earlier". A card opens what it is about and marks the
 * notice read; on a phone a swipe right marks it read and a swipe left
 * deletes it. "Mark all read" sits by the title, the rarer "Delete all" and
 * the settings in the menu beside it.
 */
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

/** One clock for every card, so "5 min ago" moves on while the page is open. */
const now = useNow({ interval: 60_000 })
const groups = computed(() => groupByDay(filtered.value, now.value))

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

/** A card was clicked: it opens by itself when it is a link; reading it is ours. */
function handleOpen(n: NotificationItem) {
  if (!n.is_read) void notificationStore.markAsRead(n.id)
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
  // Don't treat taps on the action buttons as the start of a swipe.
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

/** A swipe that ends over a card is no click on it: the link must not open. */
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
  <div class="mx-auto max-w-2xl space-y-4">
    <!-- Header: the title, "Mark all read", and the rarer actions in a menu -->
    <div class="flex items-end justify-between gap-3">
      <h1
        data-testid="page-heading"
        class="text-[26px] leading-tight font-bold tracking-tight sm:text-3xl"
      >
        {{ t('notifications.inboxTitle') }}
      </h1>
      <div class="-mr-2 flex items-center">
        <button
          v-if="hasUnread"
          type="button"
          class="text-primary hover:text-primary/80 focus-visible:ring-ring min-h-11 cursor-pointer rounded-md px-2 text-sm font-bold transition-colors focus-visible:ring-2 focus-visible:outline-none"
          data-testid="btn-notifications-read-all"
          @click="handleMarkAllAsRead"
        >
          {{ t('notifications.markAllRead') }}
        </button>
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button
              variant="ghost"
              size="icon"
              class="size-11"
              :aria-label="t('notifications.moreActions')"
              data-testid="btn-notifications-menu"
            >
              <Ellipsis class="size-5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" class="min-w-56">
            <DropdownMenuItem class="min-h-11 md:min-h-0" @select="goToPreferences">
              <Settings />
              {{ t('notifications.managePreferences') }}
            </DropdownMenuItem>
            <DropdownMenuItem
              v-if="hasAny"
              class="text-destructive focus:text-destructive min-h-11 md:min-h-0"
              data-testid="btn-notifications-delete-all"
              @select="handleDismissAll"
            >
              <Trash2 class="text-destructive" />
              {{ t('notifications.deleteAll') }}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
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

    <!-- Initial load: skeleton cards mirroring real entries. -->
    <ul
      v-if="initialLoading"
      aria-busy="true"
      :aria-label="t('notifications.title')"
      class="space-y-2 pt-2"
    >
      <li v-for="i in 3" :key="i" class="bg-card/60 flex gap-3 rounded-2xl border p-3.5">
        <Skeleton class="size-10.5 shrink-0 rounded-xl" />
        <div class="min-w-0 flex-1">
          <Skeleton class="mb-2 h-4 w-2/3" />
          <Skeleton class="mb-2 h-3 w-5/6" />
          <Skeleton class="h-3 w-16" />
        </div>
      </li>
    </ul>

    <!-- Empty state -->
    <div
      v-else-if="filtered.length === 0"
      class="bg-card border-border rounded-2xl border px-4 py-12 text-center"
    >
      <Bell class="text-muted-foreground mx-auto mb-2 h-8 w-8" />
      <p class="text-muted-foreground text-sm">{{ t('notifications.empty') }}</p>
    </div>

    <!-- The notices, under the day they came -->
    <template v-else>
      <section
        v-for="group in groups"
        :key="group.key"
        :aria-labelledby="`inbox-group-${group.key}`"
        data-testid="notification-group"
      >
        <h2
          :id="`inbox-group-${group.key}`"
          class="text-muted-foreground mt-2 mb-2 text-xs font-bold tracking-wide uppercase"
        >
          {{ t(`notifications.groups.${group.key}`) }}
        </h2>
        <ul class="space-y-2">
          <li v-for="n in group.items" :key="n.id" class="relative overflow-hidden rounded-2xl">
            <!-- What a swipe does, revealed under the card -->
            <div
              v-if="swipingId === n.id"
              class="pointer-events-none absolute inset-0 flex items-center justify-between rounded-2xl px-5 sm:hidden"
              :class="
                swipeOffset > 0
                  ? 'bg-primary/15 text-primary'
                  : swipeOffset < 0
                    ? 'bg-destructive/15 text-destructive'
                    : ''
              "
            >
              <CheckCheck v-if="swipeOffset > 0" class="h-5 w-5" />
              <span v-else />
              <Trash2 v-if="swipeOffset < 0" class="h-5 w-5" />
              <span v-else />
            </div>

            <div
              class="bg-background relative touch-pan-y"
              :style="rowTransform(n.id)"
              @click.capture="onRowClickCapture($event)"
              @pointerdown="onPointerDown(n, $event)"
              @pointermove="onPointerMove(n, $event)"
              @pointerup="onPointerUp(n)"
              @pointercancel="resetSwipe"
            >
              <NotificationRow
                :notification="n"
                :now="now"
                @open="handleOpen(n)"
                @read="handleMarkAsRead(n.id)"
                @dismiss="handleDismiss(n.id)"
              />
            </div>
          </li>
        </ul>
      </section>
    </template>

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
