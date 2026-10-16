<script setup lang="ts">
import { type Component, computed, ref } from 'vue'

import {
  BarChart3,
  Bell,
  BookCheck,
  CalendarCheck,
  CalendarDays,
  CalendarRange,
  Database,
  House,
  Menu,
  Sparkles,
  Users,
} from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

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
const router = useRouter()
const authStore = useAuthStore()
const notificationStore = useNotificationStore()
const { hasNewVersions } = useChangelogStatus()

const moreOpen = ref(false)

interface MoreItem {
  routeName: string
  labelKey: string
  icon: Component
}

/**
 * Everything the desktop sidebar offers that the three tabs do not. Phones have
 * no sidebar button, so this sheet is the only way to these pages.
 */
const moreItems = computed<MoreItem[]>(() => {
  const items: MoreItem[] = [
    { routeName: 'home', labelKey: 'navigation.sidebar.items.home.label', icon: House },
    {
      routeName: 'availability',
      labelKey: 'navigation.sidebar.items.availability.label',
      icon: CalendarCheck,
    },
  ]
  if (authStore.isManager) {
    items.push(
      { routeName: 'reporting', labelKey: 'admin.reporting.title', icon: BarChart3 },
      { routeName: 'my-events', labelKey: 'admin.events.title', icon: CalendarRange },
    )
  }
  if (authStore.isAdmin) {
    items.push(
      { routeName: 'admin-users', labelKey: 'admin.users.title', icon: Users },
      { routeName: 'admin-demo-data', labelKey: 'admin.demoData.title', icon: Database },
    )
  }
  items.push({ routeName: 'changelog', labelKey: 'changelog.title', icon: Sparkles })
  return items
})

// Home is where the app opens, so "More" lighting up there would read as if the
// user had wandered somewhere.
const moreRoutes = computed(
  () => new Set(moreItems.value.map((item) => item.routeName).filter((name) => name !== 'home')),
)

function openPage(routeName: string) {
  moreOpen.value = false
  void router.push({ name: routeName })
}

const TASK_ROUTES = new Set([
  'tasks',
  'task-create',
  'task-edit',
  'task-detail',
  'task-add-shifts',
])
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
      @click="moreOpen = true"
    >
      <div class="relative">
        <Menu class="size-5" />
        <span
          v-if="hasNewVersions"
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
      <ul class="overflow-y-auto px-2 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <li v-for="item in moreItems" :key="item.routeName">
          <button
            type="button"
            class="flex w-full items-center gap-3 rounded-md px-3 py-3 text-left text-sm transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
            :class="route.name === item.routeName ? 'bg-accent/50 font-medium' : ''"
            :data-testid="`mobile-more-${item.routeName}`"
            @click="openPage(item.routeName)"
          >
            <component :is="item.icon" class="size-5 shrink-0 text-muted-foreground" />
            <span class="flex-1">{{ t(item.labelKey) }}</span>
            <span
              v-if="item.routeName === 'changelog' && hasNewVersions"
              class="size-2 rounded-full bg-primary"
            />
          </button>
        </li>
      </ul>
    </DrawerContent>
  </Drawer>
</template>
