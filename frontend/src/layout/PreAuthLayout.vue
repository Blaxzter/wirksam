<script setup lang="ts">
import { ref } from 'vue'

import { useColorMode } from '@vueuse/core'
import { InfoIcon, MenuIcon, MoonIcon, SunIcon, UserIcon, WorkflowIcon } from 'lucide-vue-next'
import { RouterView, useRoute, useRouter } from 'vue-router'

import logo from '@/assets/logo/logo.svg'

import { useAuthStore } from '@/stores/auth'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'

import ErrorBoundary from '@/components/utils/ErrorBoundary.vue'
import LanguageSwitch from '@/components/utils/LanguageSwitch.vue'

const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()
const mode = useColorMode()

const mobileMenuOpen = ref(false)

// Toggle between fixed header with scrollable content vs full-height layout
const useFixedHeader = ref(true)

const navItems = [
  { name: 'about', label: 'preauth.layout.navigation.about', icon: InfoIcon },
  { name: 'how-it-works', label: 'preauth.layout.navigation.howItWorks', icon: WorkflowIcon },
]

const navigateToLanding = () => {
  router.push({ name: 'landing' })
}

const handleGetStarted = () => {
  const redirectUri = import.meta.env.VITE_AUTH0_CALLBACK_URL || `${window.location.origin}/app/home`
  authStore.auth0.loginWithRedirect({
    authorizationParams: {
      redirect_uri: redirectUri,
    },
  })
}

function mobileNavigate(name: string) {
  mobileMenuOpen.value = false
  router.push({ name })
}
</script>

<template>
  <div
    :class="useFixedHeader ? 'h-screen flex flex-col' : 'min-h-screen bg-background flex flex-col'"
  >
    <!-- Header for unauthenticated users -->
    <header :class="useFixedHeader ? 'border-b flex-shrink-0' : 'border-b'">
      <div class="max-w-7xl w-full mx-auto px-4 py-3 flex items-center justify-between">
        <div class="flex items-center space-x-2 min-w-0">
          <button
            @click="navigateToLanding"
            class="flex items-center gap-2 text-2xl font-bold hover:opacity-80 transition-opacity"
          >
            <img
              :src="logo"
              alt="Logo"
              class="h-10 w-10 sm:h-16 sm:w-16 shrink-0"
            />
            <span class="text-xl sm:text-2xl">{{ $t('preauth.layout.appName') }}</span>
          </button>
        </div>

        <!-- Desktop nav -->
        <nav class="hidden md:flex items-center space-x-2">
          <LanguageSwitch variant="ghost" size="sm" :show-text="false" />

          <Button
            variant="ghost"
            size="sm"
            @click="mode = mode === 'dark' ? 'light' : 'dark'"
            :aria-label="mode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'"
          >
            <SunIcon v-if="mode === 'dark'" class="h-4 w-4" />
            <MoonIcon v-else class="h-4 w-4" />
          </Button>

          <Button
            v-for="item in navItems"
            :key="item.name"
            variant="ghost"
            @click="router.push({ name: item.name })"
            :class="{
              'bg-muted font-semibold': route.name === item.name,
            }"
          >
            {{ $t(item.label) }}
          </Button>

          <div v-if="authStore.isAuthenticated" class="border-l">
            <div
              class="flex items-center space-x-3 ml-4 p-1 cursor-pointer hover:bg-muted rounded"
              @click="router.push({ name: 'home' })"
            >
              <Avatar class="h-8 w-8">
                <AvatarImage
                  :src="authStore.user?.picture || ''"
                  :alt="authStore.user?.name || authStore.user?.email || 'User'"
                />
                <AvatarFallback>
                  <UserIcon class="h-4 w-4" />
                </AvatarFallback>
              </Avatar>
              <div class="flex flex-col">
                <span class="text-sm font-medium">{{
                  authStore.user?.name || authStore.user?.email
                }}</span>
                <div class="text-xs p-0 h-auto justify-start">
                  {{ $t('preauth.layout.navigation.goToDashboard') }}
                </div>
              </div>
            </div>
          </div>

          <Button v-else @click="handleGetStarted">{{
            $t('preauth.layout.navigation.signIn')
          }}</Button>
        </nav>

        <!-- Mobile nav -->
        <div class="flex md:hidden items-center gap-1">
          <LanguageSwitch variant="ghost" size="sm" :show-text="false" />

          <Button
            variant="ghost"
            size="sm"
            @click="mode = mode === 'dark' ? 'light' : 'dark'"
            :aria-label="mode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'"
          >
            <SunIcon v-if="mode === 'dark'" class="h-4 w-4" />
            <MoonIcon v-else class="h-4 w-4" />
          </Button>

          <Sheet v-model:open="mobileMenuOpen">
            <SheetTrigger as-child>
              <Button variant="ghost" size="icon">
                <MenuIcon class="h-5 w-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="right" class="w-72 flex flex-col">
              <SheetHeader>
                <SheetTitle>{{ $t('preauth.layout.appName') }}</SheetTitle>
              </SheetHeader>
              <div class="flex flex-col gap-1 mt-4">
                <Button
                  v-for="item in navItems"
                  :key="item.name"
                  variant="ghost"
                  class="justify-start gap-3"
                  :class="{ 'bg-muted font-semibold': route.name === item.name }"
                  @click="mobileNavigate(item.name)"
                >
                  <component :is="item.icon" class="h-4 w-4" />
                  {{ $t(item.label) }}
                </Button>
              </div>

              <div class="mt-auto">
                <Separator class="mb-4" />

                <div v-if="authStore.isAuthenticated">
                  <div
                    class="flex flex-col items-center gap-2 p-3 cursor-pointer hover:bg-muted rounded"
                    @click="mobileNavigate('home')"
                  >
                    <Avatar class="h-8 w-8">
                      <AvatarImage
                        :src="authStore.user?.picture || ''"
                        :alt="authStore.user?.name || authStore.user?.email || 'User'"
                      />
                      <AvatarFallback>
                        <UserIcon class="h-4 w-4" />
                      </AvatarFallback>
                    </Avatar>
                    <div class="flex flex-col items-center">
                      <span class="text-sm font-medium">{{
                        authStore.user?.name || authStore.user?.email
                      }}</span>
                      <span class="text-xs text-muted-foreground">
                        {{ $t('preauth.layout.navigation.goToDashboard') }}
                      </span>
                    </div>
                  </div>
                </div>

                <Button v-else @click="handleGetStarted" class="w-full">
                  {{ $t('preauth.layout.navigation.signIn') }}
                </Button>
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>

    <!-- Main content area for unauthenticated views -->
    <main :class="useFixedHeader ? 'flex-1 overflow-auto flex flex-col' : 'flex-1 flex flex-col'">
      <div class="max-w-7xl w-full mx-auto px-4 py-8 flex-1">
        <ErrorBoundary>
          <RouterView />
        </ErrorBoundary>
      </div>

      <!-- Footer for unauthenticated users -->
      <footer class="border-t mt-auto flex-shrink-0">
        <div class="max-w-7xl w-full mx-auto px-4 py-6 text-center text-muted-foreground">
          <p>{{ $t('preauth.layout.footer.copyright') }}</p>
        </div>
      </footer>
    </main>
  </div>
</template>

<style scoped></style>
