<script setup lang="ts">
import { computed, onMounted } from 'vue'

import { useColorMode } from '@vueuse/core'
import {
  BarChart3,
  BookCheck,
  CalendarDays,
  CalendarRange,
  Database,
  House,
  Users,
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import wirksamDarkLogo from '@/assets/logo/wirksam-dark.svg'
import wirksamLightLogo from '@/assets/logo/wirksam-light.svg'

import { useAuthStore } from '@/stores/auth'
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

import NavMain from '@/components/navigation/NavMain.vue'
import type { NavSubItem } from '@/components/navigation/NavMain.vue'
import NavUser from '@/components/navigation/NavUser.vue'

interface AppSidebarProps extends SidebarProps {
  open?: boolean
}

const props = withDefaults(defineProps<AppSidebarProps>(), {
  collapsible: 'icon',
  open: true,
})

const { t } = useI18n()
const authStore = useAuthStore()
const sidebarStore = useSidebarStore()
const { isMobile, setOpenMobile } = useSidebar()
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
 * Compute urgency badge variant for an event based on its next open slot.
 * - Within 15 min → destructive (red)
 * - Today → default (primary)
 * - Otherwise → secondary (neutral)
 */
function eventBadge(
  openSlots: number,
  nextDate: string | null,
  nextTime: string | null,
): NavSubItem['badge'] | undefined {
  if (openSlots <= 0) return undefined

  const label = `${openSlots}`
  const tooltip = t('navigation.sidebar.badges.openSlots', { count: openSlots })
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

function formatBookingTitle(slotDate: string, slotTitle: string): string {
  const d = new Date(slotDate + 'T00:00:00')
  const formatted = d.toLocaleDateString(undefined, {
    weekday: 'short',
    day: '2-digit',
    month: '2-digit',
  })
  return `${formatted} — ${slotTitle}`
}

const navMain = computed(() => {
  const groupItems: NavSubItem[] = sidebarStore.eventGroups.map((g) => ({
    title: g.name,
    routeName: 'event-group-detail',
    routeParams: { groupId: g.id },
  }))

  const eventItems: NavSubItem[] = sidebarStore.events.map((e) => ({
    title: e.name,
    routeName: 'event-detail',
    routeParams: { eventId: e.id },
    badge: eventBadge(e.open_slots, e.next_slot_date ?? null, e.next_slot_start_time ?? null),
  }))

  const bookingItems: NavSubItem[] = sidebarStore.bookings.map((b) => ({
    title: formatBookingTitle(b.slot_date, b.slot_title),
    routeName: 'event-detail',
    routeParams: { eventId: b.event_id },
  }))

  return [
    {
      title: 'Event Groups',
      titleKey: 'navigation.sidebar.items.eventGroups.label',
      icon: CalendarRange,
      routeName: 'event-groups',
      isActive: groupItems.length > 0,
      items: groupItems,
    },
    {
      title: 'Events',
      titleKey: 'navigation.sidebar.items.events.label',
      icon: CalendarDays,
      routeName: 'events',
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
  ]
})

const navAdmin = computed(() =>
  authStore.isAdmin
    ? [
        {
          title: 'User Management',
          titleKey: 'admin.users.title',
          icon: Users,
          routeName: 'admin-users',
        },
        {
          title: 'Reports',
          titleKey: 'admin.reporting.title',
          icon: BarChart3,
          routeName: 'admin-reporting',
        },
        {
          title: 'Demo Data',
          titleKey: 'admin.demoData.title',
          icon: Database,
          routeName: 'admin-demo-data',
        },
      ]
    : [],
)
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
      >
        <img :src="currentLogo" alt="WirkSam" class="w-auto" />
      </RouterLink>
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
      </SidebarMenu>
      <NavMain :items="navMain" :open="props.open" />
    </SidebarContent>
    <NavMain
      v-if="navAdmin.length > 0"
      :items="navAdmin"
      :open="props.open"
      group-label-key="admin.sidebar.section"
      class="shrink-0 px-2 pb-2"
    />
    <SidebarFooter class="flex flex-col gap-1 p-2 pb-1">
      <NavUser />
      <RouterLink
        :to="{ name: 'changelog' }"
        data-testid="sidebar-version-link"
        class="inline-flex items-center justify-center gap-1 w-full text-[10px] text-muted-foreground/50 hover:text-muted-foreground transition-colors pb-1 group-data-[collapsible=icon]:hidden"
      >
        <span>WirkSam {{ appVersion }}</span>
        <span v-if="hasNewVersions" class="size-1.5 rounded-full bg-primary" />
      </RouterLink>
    </SidebarFooter>
    <SidebarRail />
  </Sidebar>
</template>
