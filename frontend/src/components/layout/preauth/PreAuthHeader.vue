<script setup lang="ts">
import { ref } from 'vue'

import { InfoIcon, MenuIcon, WorkflowIcon } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'

import logo from '@/assets/logo/logo.svg'

import { useAuthStore } from '@/stores/auth'

import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'

import ThemeToggle from '@/components/layout/ThemeToggle.vue'
import UserDashboardLink from '@/components/layout/preauth/UserDashboardLink.vue'
import LanguageSwitch from '@/components/utils/LanguageSwitch.vue'

defineProps<{
  useFixedHeader: boolean
}>()

const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()

const mobileMenuOpen = ref(false)

const navItems = [
  { name: 'about', label: 'preauth.layout.navigation.about', icon: InfoIcon },
  { name: 'how-it-works', label: 'preauth.layout.navigation.howItWorks', icon: WorkflowIcon },
]

const navigateToLanding = () => {
  router.push({ name: 'landing' })
}

const handleGetStarted = () => {
  const redirectUri =
    import.meta.env.VITE_AUTH0_CALLBACK_URL || `${window.location.origin}/app/home`
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
  <header :class="useFixedHeader ? 'border-b flex-shrink-0' : 'border-b'">
    <div class="max-w-7xl w-full mx-auto px-4 py-3 flex items-center justify-between">
      <div class="flex items-center space-x-2 min-w-0">
        <button
          @click="navigateToLanding"
          class="flex items-center gap-2 text-2xl font-bold hover:opacity-80 transition-opacity"
        >
          <img :src="logo" alt="Logo" class="h-10 w-10 sm:h-16 sm:w-16 shrink-0" />
          <span class="text-xl sm:text-2xl">{{ $t('preauth.layout.appName') }}</span>
        </button>
      </div>

      <!-- Desktop nav -->
      <nav class="hidden md:flex items-center space-x-2">
        <LanguageSwitch variant="ghost" size="sm" :show-text="false" />
        <ThemeToggle />

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

        <div v-if="authStore.isAuthenticated" class="border-l ml-4">
          <UserDashboardLink class="ml-4" @navigate="router.push({ name: 'home' })" />
        </div>

        <Button v-else @click="handleGetStarted">{{
          $t('preauth.layout.navigation.signIn')
        }}</Button>
      </nav>

      <!-- Mobile nav -->
      <div class="flex md:hidden items-center gap-1">
        <LanguageSwitch variant="ghost" size="sm" :show-text="false" />
        <ThemeToggle />

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
                <UserDashboardLink direction="vertical" @navigate="mobileNavigate('home')" />
              </div>

              <div v-else class="w-full px-4">
                <Button @click="handleGetStarted" class="w-full mb-4">
                  {{ $t('preauth.layout.navigation.signIn') }}
                </Button>
              </div>
            </div>
          </SheetContent>
        </Sheet>
      </div>
    </div>
  </header>
</template>
