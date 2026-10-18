<script setup lang="ts">
import { computed, ref } from 'vue'

import { CircleHelpIcon, InfoIcon, LayoutGridIcon, UsersIcon, WorkflowIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { useSandboxStore } from '@/stores/sandbox'

import LandingAbout from '@/components/landing/LandingAbout.vue'
import LandingAudience from '@/components/landing/LandingAudience.vue'
import LandingCta from '@/components/landing/LandingCta.vue'
import LandingFaq from '@/components/landing/LandingFaq.vue'
import LandingFeatures from '@/components/landing/LandingFeatures.vue'
import LandingFeedback from '@/components/landing/LandingFeedback.vue'
import LandingHero from '@/components/landing/LandingHero.vue'
import LandingJourney from '@/components/landing/LandingJourney.vue'
import LandingSectionNav from '@/components/landing/LandingSectionNav.vue'
import SandboxExpiredDialog from '@/components/sandbox/SandboxExpiredDialog.vue'
import SandboxStartDialog from '@/components/sandbox/SandboxStartDialog.vue'

/**
 * The single pre-auth marketing page.
 *
 * `/about` and `/how-it-works` used to be separate views that each repeated a
 * slice of this content; they now redirect to the `#about` and `#how-it-works`
 * sections below, so there is one story in one place.
 */
const authStore = useAuthStore()
const sandboxStore = useSandboxStore()
const router = useRouter()
const { t } = useI18n()

const demoDialogOpen = ref(false)

const sections = computed(() => [
  { id: 'audience', label: t('preauth.landing.nav.audience'), icon: UsersIcon },
  { id: 'how-it-works', label: t('preauth.landing.nav.howItWorks'), icon: WorkflowIcon },
  { id: 'features', label: t('preauth.landing.nav.features'), icon: LayoutGridIcon },
  { id: 'about', label: t('preauth.landing.nav.about'), icon: InfoIcon },
  { id: 'faq', label: t('preauth.landing.nav.faq'), icon: CircleHelpIcon },
])

function signIn() {
  router.push({ name: 'login' })
}

function goToDashboard() {
  router.push({ name: 'home' })
}

function openDemo() {
  demoDialogOpen.value = true
}
</script>

<template>
  <div>
    <LandingHero
      :is-authenticated="authStore.isAuthenticated"
      :demo-enabled="sandboxStore.enabled"
      @sign-in="signIn"
      @dashboard="goToDashboard"
      @demo="openDemo"
    />

    <LandingSectionNav :items="sections" />

    <LandingAudience />
    <LandingJourney />
    <LandingFeatures />
    <LandingAbout />
    <LandingFaq :demo-enabled="sandboxStore.enabled">
      <div
        class="mt-8 flex flex-col items-center gap-2 text-center text-sm text-muted-foreground sm:flex-row sm:justify-center sm:gap-3"
      >
        <span>{{ t('preauth.landing.faq.more') }}</span>
        <RouterLink
          :to="{ name: 'alternatives' }"
          class="font-medium text-primary underline underline-offset-2"
        >
          {{ t('preauth.content.related.pages.alternatives.title') }}
        </RouterLink>
        <span class="hidden sm:inline" aria-hidden="true">·</span>
        <RouterLink
          :to="{ name: 'use-case-club-festival' }"
          class="font-medium text-primary underline underline-offset-2"
        >
          {{ t('preauth.content.related.pages.clubFestival.title') }}
        </RouterLink>
      </div>
    </LandingFaq>
    <LandingFeedback />

    <LandingCta
      :is-authenticated="authStore.isAuthenticated"
      :demo-enabled="sandboxStore.enabled"
      @sign-in="signIn"
      @dashboard="goToDashboard"
      @demo="openDemo"
    />

    <SandboxStartDialog v-model:open="demoDialogOpen" />

    <!-- Only ever opens for somebody whose demo was swept away while they were
         using it; it reads the breadcrumb `lib/auth-session.ts` leaves behind. -->
    <SandboxExpiredDialog @start-another="openDemo" />
  </div>
</template>
