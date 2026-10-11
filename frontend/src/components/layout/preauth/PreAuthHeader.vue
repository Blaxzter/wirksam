<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'

import logo from '@/assets/logo/logo.svg'

import { useAuthStore } from '@/stores/auth'

import { isSwitchOn, useAppConfig } from '@/composables/useAppConfig'

import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'

import AppearanceMenu from '@/components/layout/AppearanceMenu.vue'
import UserDashboardLink from '@/components/layout/preauth/UserDashboardLink.vue'
import LanguageSwitch from '@/components/utils/LanguageSwitch.vue'

import { scrollToSection } from '@/lib/scroll-to-section'

const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()

/**
 * Section links for the header, on wide screens only.
 *
 * There is no mobile menu. The pre-auth pages are one scrolling document, so a
 * burger sheet with a focus trap only offered a slower way to do what scrolling
 * already does — and it was the only thing standing between a phone visitor and
 * the sign-in button. Small screens get the controls inline instead, and the
 * sections are reached by scrolling.
 */
const sections = [
  { hash: 'how-it-works', label: 'preauth.layout.navigation.howItWorks' },
  { hash: 'features', label: 'preauth.layout.navigation.features' },
  { hash: 'about', label: 'preauth.layout.navigation.about' },
] as const

/** Without a landing page (`LANDING_ENABLED=false`) there are no sections to link to. */
const landingEnabled = isSwitchOn(useAppConfig().LANDING_ENABLED)

function goToSection(hash: string) {
  // Already on the landing page: scroll rather than route, so re-picking the
  // current section still moves and no navigation is silently dropped as a
  // duplicate. From anywhere else, route and let scrollBehavior land the hash.
  if (route.name === 'landing' && scrollToSection(hash)) return
  router.push({ name: 'landing', hash: `#${hash}` })
}

function navigateToLanding() {
  router.push({ name: 'landing' })
}

function goToDashboard() {
  router.push({ name: 'home' })
}

function handleGetStarted() {
  router.push({ name: 'login' })
}
</script>

<template>
  <header class="sticky top-0 z-40 border-b bg-background/85 backdrop-blur">
    <!-- Tighter gutters on phones: at 320px the wordmark and the three controls
         want every pixel, and the gutter is the cheapest thing to give up. -->
    <div class="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-3 sm:px-6">
      <!-- Named explicitly: the image is decorative, so without this the button
           would be announced from its text alone. -->
      <button
        class="flex shrink-0 items-center gap-1.5 transition-opacity hover:opacity-80 sm:gap-2"
        :aria-label="$t('preauth.layout.appName')"
        @click="navigateToLanding"
      >
        <!-- Mark and wordmark both shrink a step on phones. The name is the
             brand and stays at every width; it is the surrounding controls that
             give way, not this. -->
        <img :src="logo" alt="" class="size-8 shrink-0 rounded-lg sm:size-9" />
        <span class="text-base font-bold whitespace-nowrap sm:text-xl">
          {{ $t('preauth.layout.appName') }}
        </span>
      </button>

      <nav class="flex items-center gap-0.5 sm:gap-1">
        <!-- The responsive display lives on this wrapper, not on the buttons.
             `cn()` merges `hidden` over the variant's own `inline-flex`, and
             Tailwind emits `hidden` after the `md:` media block — so
             `hidden md:inline-flex` on a Button is `display: none` at every
             width, which silently removed these links from the desktop header. -->
        <div v-if="landingEnabled" class="hidden items-center gap-1 md:flex">
          <Button
            v-for="section in sections"
            :key="section.hash"
            variant="ghost"
            size="sm"
            @click="goToSection(section.hash)"
          >
            {{ $t(section.label) }}
          </Button>
        </div>

        <Separator v-if="landingEnabled" orientation="vertical" class="mx-2 hidden h-6 md:block" />

        <LanguageSwitch variant="ghost" size="sm" :show-text="false" />
        <AppearanceMenu />

        <UserDashboardLink
          v-if="authStore.isAuthenticated"
          class="sm:ml-2"
          @navigate="goToDashboard"
        />
        <Button v-else size="sm" class="sm:ml-2" @click="handleGetStarted">
          {{ $t('preauth.layout.navigation.signIn') }}
        </Button>
      </nav>
    </div>
  </header>
</template>
