<script setup lang="ts">
import { ref } from 'vue'

import { ArrowRightIcon, ChevronRightIcon, FlaskConicalIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { useSandboxStore } from '@/stores/sandbox'

import { Button } from '@/components/ui/button'

import LandingCta from '@/components/landing/LandingCta.vue'
import LandingSection from '@/components/landing/LandingSection.vue'
import SectionHeading from '@/components/landing/SectionHeading.vue'
import SandboxStartDialog from '@/components/sandbox/SandboxStartDialog.vue'

/**
 * The frame around a content page (comparison, use cases): a breadcrumb back
 * to the landing page, the `h1` with an answer-first lede, the same two calls
 * to action as the landing hero, the page's own sections in the slot, and the
 * closing call to action.
 *
 * The demo button and its dialog follow `SANDBOX_ENABLED` through the sandbox
 * store, exactly like the landing page, so a deployment without the demo never
 * shows a button the backend would refuse.
 */
defineProps<{
  eyebrow: string
  title: string
  /** The first paragraph, which should already answer the page's question. */
  lede: string
  /** Short page name for the breadcrumb, matching the prerendered BreadcrumbList. */
  breadcrumb: string
  /** Heading of the closing call to action; the landing page's when omitted. */
  ctaTitle?: string
}>()

const authStore = useAuthStore()
const sandboxStore = useSandboxStore()
const router = useRouter()
const { t } = useI18n()

const demoDialogOpen = ref(false)

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
    <LandingSection id="intro" tone="tinted">
      <nav :aria-label="t('preauth.content.breadcrumbLabel')" class="flex justify-center">
        <ol class="flex items-center gap-1.5 text-sm text-muted-foreground">
          <li>
            <RouterLink :to="{ name: 'landing' }" class="transition-colors hover:text-foreground">
              {{ t('preauth.layout.appName') }}
            </RouterLink>
          </li>
          <li aria-hidden="true"><ChevronRightIcon class="size-3.5" /></li>
          <li aria-current="page" class="font-medium text-foreground">{{ breadcrumb }}</li>
        </ol>
      </nav>

      <SectionHeading level="h1" :eyebrow="eyebrow" :title="title" :lede="lede" class="mt-6" />

      <div class="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
        <Button
          data-testid="content-cta-primary"
          size="lg"
          class="w-full gap-2 sm:w-auto"
          @click="authStore.isAuthenticated ? goToDashboard() : signIn()"
        >
          {{
            authStore.isAuthenticated
              ? t('preauth.layout.navigation.goToDashboard')
              : t('preauth.landing.hero.ctaPrimary')
          }}
          <ArrowRightIcon class="size-4" />
        </Button>
        <Button
          v-if="sandboxStore.enabled"
          data-testid="content-cta-demo"
          variant="outline"
          size="lg"
          class="w-full gap-2 sm:w-auto"
          @click="openDemo"
        >
          <FlaskConicalIcon class="size-4" />
          {{ t('preauth.landing.hero.ctaDemo') }}
        </Button>
      </div>
      <p v-if="sandboxStore.enabled" class="mt-3 text-center text-sm text-muted-foreground">
        {{ t('sandbox.cta.note') }}
      </p>
    </LandingSection>

    <slot />

    <LandingCta
      :is-authenticated="authStore.isAuthenticated"
      :demo-enabled="sandboxStore.enabled"
      :title="ctaTitle"
      @sign-in="signIn"
      @dashboard="goToDashboard"
      @demo="openDemo"
    />

    <SandboxStartDialog v-model:open="demoDialogOpen" />
  </div>
</template>
