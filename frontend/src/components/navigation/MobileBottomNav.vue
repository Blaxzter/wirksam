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
  Ticket,
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
 * Every page the desktop sidebar offers that the tabs do not, in the
 * sidebar's groups. Phones have no sidebar, so this sheet is the one place for
 * pages; the avatar menu in the header keeps only what is about the user
 * (account, notifications, theme, sign out), as on desktop.
 */
const moreGroups = computed<MoreItem[][]>(() => {
  // Home is a tab of its own, so the event group starts empty; it is never
  // empty in the end, because availability and change-event always follow.
  const event: MoreItem[] = []
  // Same rule as the sidebar: once a task earns vouchers or takes them.
  const selected = authStore.selectedEvent
  if ((selected?.voucher_task_count ?? 0) > 0 || (selected?.voucher_point_count ?? 0) > 0) {
    event.push({
      routeName: 'my-vouchers',
      labelKey: 'navigation.sidebar.items.vouchers.label',
      icon: Ticket,
    })
  }
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

const moreRoutes = computed(() => new Set(moreGroups.value.flat().map((item) => item.routeName)))

// The entries are real links, so the tap itself navigates; the sheet closes on
// that tap and, as a backstop, whenever the route changes underneath it.
watch(
  () => route.fullPath,
  () => {
    moreOpen.value = false
  },
)

type Tab = 'home' | 'tasks' | 'bookings' | 'inbox' | 'more'

/** The four tabs that are plain links; "More" is a button and comes last. */
const linkTabs: {
  id: Exclude<Tab, 'more'>
  routeName: string
  labelKey: string
  icon: Component
}[] = [
  { id: 'home', routeName: 'home', labelKey: 'navigation.mobileBottomNav.home', icon: House },
  {
    id: 'tasks',
    routeName: 'tasks',
    labelKey: 'navigation.mobileBottomNav.tasks',
    icon: CalendarDays,
  },
  {
    id: 'bookings',
    routeName: 'my-bookings',
    labelKey: 'navigation.mobileBottomNav.bookings',
    icon: BookCheck,
  },
  {
    id: 'inbox',
    routeName: 'notifications',
    labelKey: 'navigation.mobileBottomNav.inbox',
    icon: Bell,
  },
]

const TASK_ROUTES = new Set(['tasks', 'task-create', 'task-edit', 'task-detail', 'task-add-shifts'])
const BOOKING_ROUTES = new Set(['my-bookings', 'booking-detail'])
const INBOX_ROUTES = new Set(['notifications'])
// The redeem page is not an entry of its own in the sheet, so `moreRoutes`
// alone would leave it with no tab lit.
const VOUCHER_ROUTES = new Set(['my-vouchers', 'voucher-redeem'])

const activeTab = computed<Tab | null>(() => {
  const name = typeof route.name === 'string' ? route.name : ''
  if (name === 'home') return 'home'
  if (TASK_ROUTES.has(name)) return 'tasks'
  if (BOOKING_ROUTES.has(name)) return 'bookings'
  if (INBOX_ROUTES.has(name)) return 'inbox'
  if (VOUCHER_ROUTES.has(name)) return 'more'
  if (moreRoutes.value.has(name)) return 'more'
  return null
})

/**
 * Said explicitly on every tab: RouterLink's own `aria-current` only fires on
 * an exact match, so a task's detail page would light the Tasks tab without
 * announcing it.
 */
const currentFor = (tab: Tab) => (activeTab.value === tab ? 'page' : undefined)

const TAB_CLASS = 'flex h-16 min-w-0 flex-1 flex-col items-center justify-center gap-0.5'
const PILL_CLASS = 'relative flex h-7 w-[52px] items-center justify-center rounded-full'
const LABEL_CLASS = 'max-w-full truncate px-1 text-[11px]'

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
      v-for="tab in linkTabs"
      :key="tab.id"
      :to="{ name: tab.routeName }"
      :data-testid="`mobile-nav-${tab.id}`"
      :aria-current="currentFor(tab.id)"
      :class="[
        TAB_CLASS,
        activeTab === tab.id ? 'text-primary' : 'text-muted-foreground hover:text-foreground',
      ]"
    >
      <span :class="[PILL_CLASS, activeTab === tab.id ? 'bg-primary/10' : '']">
        <component :is="tab.icon" class="size-5" aria-hidden="true" />
        <span
          v-if="tab.id === 'inbox' && notificationStore.hasUnread"
          class="absolute top-0 right-2 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-700 px-1 text-[10px] font-bold text-white"
        >
          {{ notificationDisplayCount }}
        </span>
      </span>
      <span :class="[LABEL_CLASS, activeTab === tab.id ? 'font-semibold' : 'font-medium']">
        {{ t(tab.labelKey) }}
      </span>
    </RouterLink>

    <button
      type="button"
      data-testid="mobile-nav-more"
      :class="[
        TAB_CLASS,
        activeTab === 'more' || moreOpen
          ? 'text-primary'
          : 'text-muted-foreground hover:text-foreground',
      ]"
      :aria-expanded="moreOpen"
      :aria-label="
        teamRequestCount > 0
          ? t('teams.nav.moreWaiting', { count: teamRequestCount }, teamRequestCount)
          : undefined
      "
      @click="moreOpen = true"
    >
      <span :class="[PILL_CLASS, activeTab === 'more' || moreOpen ? 'bg-primary/10' : '']">
        <Menu class="size-5" aria-hidden="true" />
        <!-- Something to decide outranks something new to read. -->
        <span
          v-if="teamRequestCount > 0"
          class="absolute top-0.5 right-3 size-2 rounded-full bg-red-700"
          data-testid="mobile-nav-more-dot"
        />
        <span
          v-else-if="hasNewVersions"
          class="absolute top-0.5 right-3 size-2 rounded-full bg-primary"
        />
      </span>
      <span
        :class="[LABEL_CLASS, activeTab === 'more' || moreOpen ? 'font-semibold' : 'font-medium']"
      >
        {{ t('navigation.mobileBottomNav.more') }}
      </span>
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
