<script setup lang="ts">
import { type Component, computed, ref, watch } from 'vue'

import {
  ArrowLeftRight,
  BarChart3,
  Bell,
  BookCheck,
  CalendarCheck,
  CalendarDays,
  CalendarRange,
  House,
  Map as MapIcon,
  Menu,
  Sparkles,
  Users,
  UsersRound,
} from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'

import { useChangelogStatus } from '@/composables/useChangelogStatus'

import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from '@/components/ui/drawer'

const { t } = useI18n()
const route = useRoute()
const authStore = useAuthStore()
const notificationStore = useNotificationStore()
const { hasNewVersions } = useChangelogStatus()

const moreOpen = ref(false)

const showTeams = computed(() => {
  const event = authStore.selectedEvent
  if (!event) return false
  return (event.team_count ?? 0) > 0 || authStore.canManageEvent(event.id)
})
/** Team requests this user may decide in the selected event. */
const teamRequestCount = computed(() => authStore.selectedEvent?.pending_team_request_count ?? 0)

interface MoreItem {
  routeName: string
  labelKey: string
  icon: Component
  query?: Record<string, string>
  /** A count to draw on the row, like the Notifications badge. */
  badge?: number
}

/**
 * Every page the desktop sidebar offers that the three tabs do not, in the
 * sidebar's groups. Phones have no sidebar, so this sheet is the one place for
 * pages; the avatar menu in the header keeps only what is about the user
 * (account, notifications, theme, sign out), as on desktop.
 */
const moreGroups = computed<MoreItem[][]>(() => {
  const event: MoreItem[] = [
    { routeName: 'home', labelKey: 'navigation.sidebar.items.home.label', icon: House },
  ]
  // Same rule as the sidebar: once the event has a team, or for whoever could
  // create the first one.
  if (showTeams.value) {
    event.push({
      routeName: 'teams',
      labelKey: 'teams.nav.label',
      icon: UsersRound,
      badge: teamRequestCount.value,
    })
  }
  // Same rule as the sidebar: only once the event has a plan with a picture.
  if ((authStore.selectedEvent?.venue_plan_count ?? 0) > 0) {
    event.push({
      routeName: 'event-map',
      labelKey: 'navigation.sidebar.items.venueMap.label',
      icon: MapIcon,
    })
  }
  event.push(
    {
      routeName: 'availability',
      labelKey: 'navigation.sidebar.items.availability.label',
      icon: CalendarCheck,
    },
    {
      routeName: 'select-event',
      labelKey: 'duties.selectEvent.changeEvent',
      icon: ArrowLeftRight,
      query: { mode: 'switch' },
    },
  )

  const manage: MoreItem[] = []
  if (authStore.isManager) {
    manage.push(
      { routeName: 'reporting', labelKey: 'admin.reporting.title', icon: BarChart3 },
      { routeName: 'my-events', labelKey: 'admin.events.title', icon: CalendarRange },
    )
  }
  if (authStore.isAdmin) {
    manage.push({ routeName: 'admin-users', labelKey: 'admin.users.title', icon: Users })
  }

  const app: MoreItem[] = [{ routeName: 'changelog', labelKey: 'changelog.title', icon: Sparkles }]
  return [event, manage, app].filter((group) => group.length > 0)
})

// Home is where the app opens, so "More" lighting up there would read as if the
// user had wandered somewhere.
const moreRoutes = computed(
  () =>
    new Set(
      moreGroups.value
        .flat()
        .map((item) => item.routeName)
        .filter((name) => name !== 'home'),
    ),
)

// The entries are real links, so the tap itself navigates; the sheet closes on
// that tap and, as a backstop, whenever the route changes underneath it.
watch(
  () => route.fullPath,
  () => {
    moreOpen.value = false
  },
)

const TASK_ROUTES = new Set(['tasks', 'task-create', 'task-edit', 'task-detail', 'task-add-shifts'])
const BOOKING_ROUTES = new Set(['my-bookings', 'booking-detail'])
const INBOX_ROUTES = new Set(['notifications'])

const activeTab = computed<'tasks' | 'bookings' | 'inbox' | 'more' | null>(() => {
  const name = typeof route.name === 'string' ? route.name : ''
  if (TASK_ROUTES.has(name)) return 'tasks'
  if (BOOKING_ROUTES.has(name)) return 'bookings'
  if (INBOX_ROUTES.has(name)) return 'inbox'
  if (moreRoutes.value.has(name)) return 'more'
  return null
})

const notificationDisplayCount = computed(() => {
  if (notificationStore.unreadCount > 99) return '99+'
  return notificationStore.unreadCount.toString()
})
</script>

<template>
  <nav
    data-testid="mobile-bottom-nav"
    class="fixed inset-x-0 bottom-0 z-40 flex items-stretch border-t bg-background pb-[env(safe-area-inset-bottom)] md:hidden"
  >
    <RouterLink
      :to="{ name: 'tasks' }"
      data-testid="mobile-nav-tasks"
      class="flex h-16 flex-1 flex-col items-center justify-center gap-0.5 text-xs"
      :class="
        activeTab === 'tasks' ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
      "
    >
      <CalendarDays class="size-5" />
      <span>{{ t('navigation.mobileBottomNav.tasks') }}</span>
    </RouterLink>

    <RouterLink
      :to="{ name: 'my-bookings' }"
      data-testid="mobile-nav-bookings"
      class="flex h-16 flex-1 flex-col items-center justify-center gap-0.5 text-xs"
      :class="
        activeTab === 'bookings' ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
      "
    >
      <BookCheck class="size-5" />
      <span>{{ t('navigation.mobileBottomNav.bookings') }}</span>
    </RouterLink>

    <RouterLink
      :to="{ name: 'notifications' }"
      data-testid="mobile-nav-inbox"
      class="relative flex h-16 flex-1 flex-col items-center justify-center gap-0.5 text-xs"
      :class="
        activeTab === 'inbox' ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
      "
    >
      <div class="relative">
        <Bell class="size-5" />
        <span
          v-if="notificationStore.hasUnread"
          class="absolute -top-1 -right-2 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-700 px-1 text-[10px] font-bold text-white"
        >
          {{ notificationDisplayCount }}
        </span>
      </div>
      <span>{{ t('navigation.mobileBottomNav.inbox') }}</span>
    </RouterLink>

    <button
      type="button"
      data-testid="mobile-nav-more"
      class="flex h-16 flex-1 flex-col items-center justify-center gap-0.5 text-xs"
      :class="
        activeTab === 'more' || moreOpen
          ? 'text-primary'
          : 'text-muted-foreground hover:text-foreground'
      "
      :aria-expanded="moreOpen"
      :aria-label="
        teamRequestCount > 0
          ? t('teams.nav.moreWaiting', { count: teamRequestCount }, teamRequestCount)
          : undefined
      "
      @click="moreOpen = true"
    >
      <div class="relative">
        <Menu class="size-5" />
        <!-- Something to decide outranks something new to read. -->
        <span
          v-if="teamRequestCount > 0"
          class="absolute -top-0.5 -right-1 size-2 rounded-full bg-red-700"
          data-testid="mobile-nav-more-dot"
        />
        <span
          v-else-if="hasNewVersions"
          class="absolute -top-0.5 -right-1 size-2 rounded-full bg-primary"
        />
      </div>
      <span>{{ t('navigation.mobileBottomNav.more') }}</span>
    </button>
  </nav>

  <Drawer v-model:open="moreOpen">
    <DrawerContent data-testid="mobile-more-sheet">
      <DrawerHeader class="px-4 pt-1 text-left">
        <DrawerTitle>{{ t('navigation.mobileBottomNav.more') }}</DrawerTitle>
        <DrawerDescription class="sr-only">
          {{ t('navigation.mobileBottomNav.moreDescription') }}
        </DrawerDescription>
      </DrawerHeader>
      <div class="overflow-y-auto px-2 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <ul
          v-for="(group, index) in moreGroups"
          :key="index"
          :class="index > 0 ? 'mt-1 border-t pt-1' : ''"
        >
          <li v-for="item in group" :key="item.routeName">
            <RouterLink
              :to="{ name: item.routeName, query: item.query }"
              class="flex w-full items-center gap-3 rounded-md px-3 py-3 text-left text-sm transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
              :class="route.name === item.routeName ? 'bg-accent/50 font-medium' : ''"
              :aria-current="route.name === item.routeName ? 'page' : undefined"
              :data-testid="`mobile-more-${item.routeName}`"
              @click="moreOpen = false"
            >
              <component :is="item.icon" class="size-5 shrink-0 text-muted-foreground" />
              <span class="flex-1">{{ t(item.labelKey) }}</span>
              <span
                v-if="item.badge"
                class="flex h-5 min-w-5 items-center justify-center rounded-full bg-red-700 px-1.5 text-[11px] font-bold text-white"
                :data-testid="`mobile-more-badge-${item.routeName}`"
              >
                <span aria-hidden="true">{{ item.badge > 99 ? '99+' : item.badge }}</span>
                <span class="sr-only">
                  {{ t('teams.nav.waiting', { count: item.badge }, item.badge) }}
                </span>
              </span>
              <span
                v-else-if="item.routeName === 'changelog' && hasNewVersions"
                class="size-2 rounded-full bg-primary"
              />
            </RouterLink>
          </li>
        </ul>
      </div>
    </DrawerContent>
  </Drawer>
</template>
