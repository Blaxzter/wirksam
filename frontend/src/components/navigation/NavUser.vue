<script setup lang="ts">
import { computed } from 'vue'

import { useColorMode } from '@vueuse/core'
import { BadgeCheck, Bell, ChevronsUpDown, Globe, LogOut, Moon, Sun } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

import { useAuthStore } from '@/stores/auth'

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
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from '@/components/ui/sidebar'

const { isMobile } = useSidebar()
const authStore = useAuthStore()
const mode = useColorMode()
useI18n()

// Get user data from Auth0
const user = computed(() => authStore.user)
const isAuthenticated = computed(() => authStore.isAuthenticated)

// Create display name - fallback hierarchy
const displayName = computed(
  () => user.value?.name || user.value?.nickname || user.value?.email || 'User',
)

// Create display email
const displayEmail = computed(() => user.value?.email || '')

// Create avatar URL
const avatarUrl = computed(() => user.value?.picture || '')

// Create initials for fallback
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
  <SidebarMenu v-if="isAuthenticated">
    <SidebarMenuItem>
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <SidebarMenuButton
            size="lg"
            class="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
            data-testid="nav-user-menu"
          >
            <Avatar class="h-8 w-8 rounded-lg">
              <AvatarImage v-if="avatarUrl" :src="avatarUrl" :alt="displayName" />
              <AvatarFallback class="rounded-lg">
                {{ initials }}
              </AvatarFallback>
            </Avatar>
            <div class="grid flex-1 text-left text-sm leading-tight">
              <span class="truncate font-medium">{{ displayName }}</span>
              <span v-if="displayEmail" class="truncate text-xs">{{ displayEmail }}</span>
            </div>
            <ChevronsUpDown class="ml-auto size-4" />
          </SidebarMenuButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          class="w-[--reka-dropdown-menu-trigger-width] min-w-56 rounded-lg"
          :side="isMobile ? 'bottom' : 'right'"
          align="end"
          :side-offset="4"
        >
          <DropdownMenuLabel class="p-0 font-normal">
            <div class="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
              <Avatar class="h-8 w-8 rounded-lg">
                <AvatarImage v-if="avatarUrl" :src="avatarUrl" :alt="displayName" />
                <AvatarFallback class="rounded-lg">
                  {{ initials }}
                </AvatarFallback>
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
            <DropdownMenuItem data-testid="nav-user-settings" @click="$router.push({ name: 'settings' })">
              <BadgeCheck />
              {{ $t('navigation.user.actions.account') }}
            </DropdownMenuItem>
            <DropdownMenuItem data-testid="nav-user-notifications" @click="$router.push({ name: 'notification-preferences' })">
              <Bell />
              {{ $t('navigation.user.actions.notifications') }}
            </DropdownMenuItem>
            <DropdownMenuItem @click="$router.push({ name: 'landing' })">
              <Globe />
              {{ $t('navigation.user.actions.landingPage') }}
            </DropdownMenuItem>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem data-testid="nav-user-logout" @click="authStore.logout">
            <LogOut />
            {{ $t('navigation.user.actions.logout') }}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </SidebarMenuItem>
  </SidebarMenu>
  <div v-else>
    <p>{{ $t('navigation.user.loginPrompt') }}</p>
  </div>
</template>
