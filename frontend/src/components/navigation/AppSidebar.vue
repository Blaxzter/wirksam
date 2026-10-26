<script setup lang="ts">
import { computed, onMounted } from 'vue'

import {
  BarChart3,
  Bell,
  BookCheck,
  CalendarCheck,
  CalendarDays,
  CalendarRange,
  ChevronsUpDown,
  House,
  Lock,
  Map as MapIcon,
  Users,
  UsersRound,
} from '@lucide/vue'
import { useColorMode } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import logoIcon from '@/assets/logo/logo.svg'
import wirksamDarkLogo from '@/assets/logo/wirksam-dark.svg'
import wirksamLightLogo from '@/assets/logo/wirksam-light.svg'

import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'
import { useSidebarStore } from '@/stores/sidebar'

import { useChangelogStatus } from '@/composables/useChangelogStatus'

import type { SidebarProps } from '@/components/ui/sidebar'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from '@/components/ui/sidebar'

import EventSwitcherMenu from '@/components/navigation/EventSwitcherMenu.vue'
import NavMain from '@/components/navigation/NavMain.vue'
import type { NavSubItem } from '@/components/navigation/NavMain.vue'
import NavUser from '@/components/navigation/NavUser.vue'
import HintTooltip from '@/components/utils/HintTooltip.vue'

interface AppSidebarProps extends SidebarProps {
  open?: boolean
}

const props = withDefaults(defineProps<AppSidebarProps>(), {
  collapsible: 'icon',
  open: true,
})

const { t, locale } = useI18n()
const authStore = useAuthStore()
const sidebarStore = useSidebarStore()
const notificationStore = useNotificationStore()

const notificationDisplayCount = computed(() => {
  if (notificationStore.unreadCount > 99) return '99+'
  return notificationStore.unreadCount.toString()
})

const showEventSwitcher = computed(() => authStore.profile?.show_event_switcher_in_nav ?? false)
const selectedEventName = computed(() => authStore.selectedEvent?.name ?? '')
const switcherLabel = computed(
  () => selectedEventName.value || t('navigation.sidebar.eventSwitcher.empty'),
)
const { isMobile, setOpenMobile, state } = useSidebar()
const router = useRouter()
const route = useRoute()
const mode = useColorMode()
const currentLogo = computed(() => (mode.value === 'light' ? wirksamDarkLogo : wirksamLightLogo))
const appVersion = __APP_VERSION__
const { hasNewVersions } = useChangelogStatus()

onMounted(() => {
  sidebarStore.fetch()
})

router.afterEach(() => {
  if (isMobile.value) {
    setOpenMobile(false)
  }
})

/**
 * Compute urgency badge variant for a task based on its next open shift.
 * - Within 15 min → destructive (red)
 * - Today → default (primary)
 * - Otherwise → secondary (neutral)
 */
function statusBadge(status: string): NavSubItem['badge'] {
  return {
    text: t(`duties.tasks.statuses.${status}`),
    tooltip: t('navigation.sidebar.badges.managersOnly'),
    variant: 'secondary',
  }
}

function eventBadge(
  openShifts: number,
  nextDate: string | null,
  nextTime: string | null,
): NavSubItem['badge'] | undefined {
  if (openShifts <= 0) return undefined

  const label = `${openShifts}`
  const tooltip = t('navigation.sidebar.badges.openShifts', { count: openShifts })
  if (!nextDate) return { text: label, tooltip, variant: 'outline' }

  const now = new Date()
  const slotDateTime = nextTime
    ? new Date(`${nextDate}T${nextTime}`)
    : new Date(`${nextDate}T23:59:59`)

  const diffMs = slotDateTime.getTime() - now.getTime()
  const diffMin = diffMs / 60_000

  if (diffMin <= 15 && diffMin > -60) return { text: label, tooltip, variant: 'destructive' }
  return { text: label, tooltip, variant: 'outline' }
}

/**
 * A task reserved for a team the viewer is not in: a lock where the count
 * would be. Its open shifts are not theirs to take, so neither the number nor
 * a red "starting soon" would help.
 */
function lockBadge(teamName: string | null | undefined): NavSubItem['badge'] {
  return {
    text: '',
    icon: Lock,
    tooltip: t('teamLocks.badge.locked', { name: teamName ?? '' }),
    variant: 'outline',
  }
}

function formatBookingDate(slotDate: string): string {
  const d = new Date(slotDate + 'T00:00:00')
  return d.toLocaleDateString(locale.value, {
    weekday: 'short',
    day: '2-digit',
    month: '2-digit',
  })
}

const showTeams = computed(() => {
  const event = authStore.selectedEvent
  if (!event) return false
  return (event.team_count ?? 0) > 0 || authStore.canManageEvent(event.id)
})
/** Team requests this user may decide in the selected event. */
const teamRequestCount = computed(() => authStore.selectedEvent?.pending_team_request_count ?? 0)

const navMain = computed(() => {
  const eventItems: NavSubItem[] = sidebarStore.tasks.map((e) => ({
    title: e.name,
    routeName: 'task-detail',
    routeParams: { eventId: e.id },
    badge:
      e.status && e.status !== 'published'
        ? statusBadge(e.status)
        : e.locked_by_team
          ? lockBadge(e.team_name)
          : eventBadge(e.open_shifts, e.next_shift_date ?? null, e.next_shift_start_time ?? null),
  }))

  const bookingItems: NavSubItem[] = sidebarStore.bookings.map((b) => ({
    title: b.slot_title,
    routeName: 'booking-detail',
    routeParams: { bookingId: b.id },
    badge: {
      text: formatBookingDate(b.slot_date),
      variant: 'secondary',
    },
  }))

  return [
    {
      title: 'Tasks',
      titleKey: 'navigation.sidebar.items.tasks.label',
      icon: CalendarDays,
      routeName: 'tasks',
      isActive: eventItems.length > 0,
      items: eventItems,
    },
    {
      title: 'My Bookings',
      titleKey: 'navigation.sidebar.items.myBookings.label',
      icon: BookCheck,
      routeName: 'my-bookings',
      isActive: bookingItems.length > 0,
      items: bookingItems,
    },
    {
      title: 'Availability',
      titleKey: 'navigation.sidebar.items.availability.label',
      icon: CalendarCheck,
      routeName: 'availability',
    },
    // Once the event has a team, or for whoever could create the first one.
    ...(showTeams.value
      ? [
          {
            title: 'Teams',
            titleKey: 'teams.nav.label',
            icon: UsersRound,
            routeName: 'teams',
            badge: teamRequestCount.value,
            badgeLabel: t(
              'teams.nav.waiting',
              { count: teamRequestCount.value },
              teamRequestCount.value,
            ),
          },
        ]
      : []),
    // Only once the event has a plan with a picture — an empty map is no help.
    ...((authStore.selectedEvent?.venue_plan_count ?? 0) > 0
      ? [
          {
            title: 'Map',
            titleKey: 'navigation.sidebar.items.venueMap.label',
            icon: MapIcon,
            routeName: 'event-map',
          },
        ]
      : []),
  ]
})

const navManager = computed(() => {
  const items = []
  if (authStore.isManager) {
    items.push({
      title: 'Reports',
      titleKey: 'admin.reporting.title',
      icon: BarChart3,
      routeName: 'reporting',
    })
  }
  return items
})

const navAdmin = computed(() => {
  const items: {
    title: string
    titleKey: string
    icon: typeof Users
    routeName: string
  }[] = []
  if (authStore.isManager) {
    items.push({
      title: 'Manage Events',
      titleKey: 'admin.events.title',
      icon: CalendarRange,
      routeName: 'my-events',
    })
  }
  if (authStore.isAdmin) {
    items.push({
      title: 'User Management',
      titleKey: 'admin.users.title',
      icon: Users,
      routeName: 'admin-users',
    })
  }
  return items
})
</script>

<template>
  <Sidebar
    :side="props.side"
    :variant="props.variant"
    :collapsible="props.collapsible"
    :class="props.class"
  >
    <SidebarHeader>
      <RouterLink
        :to="{ name: 'home' }"
        class="flex items-center gap-2 px-2 py-3 hover:opacity-80 transition-opacity"
        :class="{ 'px-0!': state === 'collapsed' }"
      >
        <img v-if="state === 'collapsed'" :src="logoIcon" alt="WirkSam" class="size-8" />
        <img v-else :src="currentLogo" alt="WirkSam" class="w-auto" />
      </RouterLink>
      <EventSwitcherMenu v-if="showEventSwitcher">
        <template #default="{ open }">
          <button
            type="button"
            data-testid="sidebar-event-switcher"
            class="group flex items-center gap-2 rounded-md border bg-card px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            :class="[
              state === 'collapsed' ? 'justify-center px-0 py-2' : '',
              open ? 'bg-accent' : '',
            ]"
            :aria-label="state === 'collapsed' ? switcherLabel : undefined"
          >
            <!-- The popover owns the button as its trigger, so the hint sits on
                 the icon, which is all the collapsed button shows. -->
            <HintTooltip v-if="state === 'collapsed'" :label="switcherLabel" side="right">
              <span class="flex w-full justify-center">
                <CalendarRange class="size-4 shrink-0 text-muted-foreground" />
              </span>
            </HintTooltip>
            <CalendarRange v-else class="size-4 shrink-0 text-muted-foreground" />
            <div v-if="state !== 'collapsed'" class="min-w-0 flex-1">
              <p class="truncate font-medium leading-tight">
                {{ selectedEventName || t('navigation.sidebar.eventSwitcher.empty') }}
              </p>
              <p class="text-xs text-muted-foreground leading-tight">
                {{ t('navigation.sidebar.eventSwitcher.hint') }}
              </p>
            </div>
            <ChevronsUpDown
              v-if="state !== 'collapsed'"
              class="size-3.5 shrink-0 text-muted-foreground"
            />
          </button>
        </template>
      </EventSwitcherMenu>
    </SidebarHeader>
    <SidebarContent>
      <!-- Home link above the Platform section -->
      <SidebarMenu class="px-2 pt-1">
        <SidebarMenuItem>
          <SidebarMenuButton
            :tooltip="t('navigation.sidebar.items.home.label')"
            :is-active="route.name === 'home'"
            as-child
          >
            <RouterLink :to="{ name: 'home' }" data-testid="sidebar-link-home">
              <House />
              <span>{{ t('navigation.sidebar.items.home.label') }}</span>
              <span
                v-if="route.name === 'home'"
                class="ml-auto size-1.5 rounded-full bg-foreground"
              />
            </RouterLink>
          </SidebarMenuButton>
        </SidebarMenuItem>
        <SidebarMenuItem>
          <SidebarMenuButton
            :tooltip="t('notifications.title')"
            :is-active="route.name === 'notifications'"
            as-child
          >
            <RouterLink :to="{ name: 'notifications' }" data-testid="sidebar-link-notifications">
              <Bell />
              <span>{{ t('notifications.title') }}</span>
              <span
                v-if="notificationStore.hasUnread"
                class="ml-auto flex h-4 min-w-4 items-center justify-center rounded-full bg-red-700 px-1 text-[10px] font-bold text-white"
              >
                {{ notificationDisplayCount }}
              </span>
              <span
                v-else-if="route.name === 'notifications'"
                class="ml-auto size-1.5 rounded-full bg-foreground"
              />
            </RouterLink>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
      <NavMain :items="navMain" :open="props.open" />
    </SidebarContent>
    <NavMain
      v-if="navManager.length > 0"
      :items="navManager"
      :open="props.open"
      event-label-key="navigation.sidebar.items.management.label"
      class="shrink-0 px-2 pb-2"
    />
    <NavMain
      v-if="navAdmin.length > 0"
      :items="navAdmin"
      :open="props.open"
      event-label-key="admin.sidebar.section"
      class="shrink-0 px-2 pb-2"
    />
    <SidebarFooter class="flex flex-col gap-1 p-2 pb-1">
      <NavUser />
      <RouterLink
        :to="{ name: 'changelog' }"
        data-testid="sidebar-version-link"
        class="inline-flex items-center justify-center gap-1 w-full text-[10px] text-muted-foreground hover:text-foreground transition-colors pb-1 event-data-[collapsible=icon]:hidden"
      >
        <span>WirkSam {{ appVersion }}</span>
        <span v-if="hasNewVersions" class="size-1.5 rounded-full bg-primary" />
      </RouterLink>
    </SidebarFooter>
    <!--
      No native `title` (shadcn ships an English one): the resize cursor is the
      hint here, and a tooltip anchored to a full-height strip would float
      mid-screen over the menu. The header's toggle carries the tooltip.
    -->
    <SidebarRail title="" :aria-label="t('navigation.sidebar.toggle')" />
  </Sidebar>
</template>
