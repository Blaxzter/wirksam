<script setup lang="ts">
import { computed } from 'vue'

import { useColorMode } from '@vueuse/core'
import {
  BadgeCheck,
  Bell,
  CalendarRange,
  Globe,
  LogOut,
  Map as MapIcon,
  Moon,
  Sun,
} from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useAvatarUrl } from '@/composables/useAvatarUrl'

import { useAuthStore } from '@/stores/auth'

import InstallAppMenuItem from '@/components/navigation/InstallAppMenuItem.vue'
import LegalMenuLinks from '@/components/navigation/LegalMenuLinks.vue'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

const authStore = useAuthStore()
const mode = useColorMode()
useI18n()

const user = computed(() => authStore.user)
const isAuthenticated = computed(() => authStore.isAuthenticated)
// Same rule as the sidebar: only once the event has a plan with a picture.
const hasVenueMap = computed(() => (authStore.selectedEvent?.venue_plan_count ?? 0) > 0)

const displayName = computed(
  () => user.value?.name || user.value?.nickname || user.value?.email || 'User',
)
const displayEmail = computed(() => user.value?.email || '')
const avatarUrl = useAvatarUrl(() => authStore.profile)
const initials = computed(() => {
  if (user.value?.name) {
    return user.value.name
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2)
  }
  if (user.value?.email) {
    return user.value.email[0].toUpperCase()
  }
  return 'U'
})
</script>

<template>
  <DropdownMenu v-if="isAuthenticated">
    <DropdownMenuTrigger as-child>
      <button
        type="button"
        class="flex size-9 items-center justify-center rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring"
        data-testid="mobile-user-menu"
      >
        <Avatar class="size-9">
          <AvatarImage v-if="avatarUrl" :src="avatarUrl" :alt="displayName" />
          <AvatarFallback>{{ initials }}</AvatarFallback>
        </Avatar>
      </button>
    </DropdownMenuTrigger>
    <DropdownMenuContent class="min-w-56 rounded-lg" side="bottom" align="end" :side-offset="4">
      <DropdownMenuLabel class="p-0 font-normal">
        <div class="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
          <Avatar class="h-8 w-8 rounded-lg">
            <AvatarImage v-if="avatarUrl" :src="avatarUrl" :alt="displayName" />
            <AvatarFallback class="rounded-lg">{{ initials }}</AvatarFallback>
          </Avatar>
          <div class="grid flex-1 text-left text-sm leading-tight">
            <span class="truncate font-semibold">{{ displayName }}</span>
            <span v-if="displayEmail" class="truncate text-xs">{{ displayEmail }}</span>
          </div>
        </div>
      </DropdownMenuLabel>

      <DropdownMenuSeparator />
      <DropdownMenuGroup>
        <DropdownMenuItem @click="mode = mode === 'dark' ? 'light' : 'dark'">
          <Sun v-if="mode === 'dark'" />
          <Moon v-else />
          {{
            mode === 'dark'
              ? $t('navigation.user.actions.switchToLight')
              : $t('navigation.user.actions.switchToDark')
          }}
        </DropdownMenuItem>
      </DropdownMenuGroup>
      <DropdownMenuSeparator />
      <DropdownMenuGroup>
        <DropdownMenuItem
          data-testid="mobile-user-settings"
          @click="$router.push({ name: 'settings' })"
        >
          <BadgeCheck />
          {{ $t('navigation.user.actions.account') }}
        </DropdownMenuItem>
        <DropdownMenuItem
          data-testid="mobile-user-notifications"
          @click="$router.push({ name: 'notification-preferences' })"
        >
          <Bell />
          {{ $t('navigation.user.actions.notifications') }}
        </DropdownMenuItem>
        <DropdownMenuItem
          v-if="hasVenueMap"
          data-testid="mobile-user-venue-map"
          @click="$router.push({ name: 'event-map' })"
        >
          <MapIcon />
          {{ $t('navigation.user.actions.venueMap') }}
        </DropdownMenuItem>
        <DropdownMenuItem
          data-testid="mobile-user-change-event"
          @click="$router.push({ name: 'select-event', query: { mode: 'switch' } })"
        >
          <CalendarRange />
          {{ $t('duties.selectEvent.changeEvent') }}
        </DropdownMenuItem>
        <DropdownMenuItem
          v-if="authStore.isManager"
          data-testid="mobile-user-manage-events"
          @click="$router.push({ name: 'my-events' })"
        >
          <CalendarRange />
          {{ $t('admin.events.title') }}
        </DropdownMenuItem>
        <InstallAppMenuItem />
        <DropdownMenuItem @click="$router.push({ name: 'landing' })">
          <Globe />
          {{ $t('navigation.user.actions.landingPage') }}
        </DropdownMenuItem>
      </DropdownMenuGroup>
      <DropdownMenuSeparator />
      <DropdownMenuItem data-testid="mobile-user-logout" @click="authStore.logout">
        <LogOut />
        {{ $t('navigation.user.actions.logout') }}
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <LegalMenuLinks />
    </DropdownMenuContent>
  </DropdownMenu>
</template>
