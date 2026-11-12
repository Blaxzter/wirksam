<script setup lang="ts">
import { ref } from 'vue'

import { ArrowRightIcon, ChevronRightIcon, FlaskConicalIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { useSandboxStore } from '@/stores/sandbox'

import { Button } from '@/components/ui/button'

import PageArt from '@/components/content/PageArt.vue'
import LandingCta from '@/components/landing/LandingCta.vue'
import LandingSection from '@/components/landing/LandingSection.vue'
import SandboxStartDialog from '@/components/sandbox/SandboxStartDialog.vue'

import type { ArtKind } from '@/lib/content-pages'

/**
 * The frame around a content page (comparison, use cases): a breadcrumb back
 * to the landing page, the `h1` with an answer-first lede, the same two calls
 * to action as the landing hero, the page's own sections in the slot, and the
 * closing call to action.
 *
 * Beside the title stands a drawing of what the page is about (`art`). The
 * page's colour (`color`) is set here as `--art`, so the header, the drawing and
 * whatever the page puts in the slot can all be drawn in it.
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
  /** The page one level up, between the landing page and this one. */
  parent?: { routeName: string; label: string }
  /** Leaves the two buttons out of the header, for a page someone reads to get a job done. */
  hideActions?: boolean
  /** The drawing beside the title. */
  art?: ArtKind
  /** The page's colour, as a CSS value; see `pageLook`. */
  color?: string
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
  <div :style="{ '--art': color ?? 'var(--chart-1)' }">
    <LandingSection id="intro" tone="accent" width="wide">
      <nav :aria-label="t('preauth.content.breadcrumbLabel')">
        <ol class="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
          <li>
            <RouterLink :to="{ name: 'landing' }" class="transition-colors hover:text-foreground">
              {{ t('preauth.layout.appName') }}
            </RouterLink>
          </li>
          <li aria-hidden="true"><ChevronRightIcon class="size-3.5" /></li>
          <template v-if="parent">
            <li>
              <RouterLink
                :to="{ name: parent.routeName }"
                class="transition-colors hover:text-foreground"
              >
                {{ parent.label }}
              </RouterLink>
            </li>
            <li aria-hidden="true"><ChevronRightIcon class="size-3.5" /></li>
          </template>
          <li aria-current="page" class="font-medium text-foreground">{{ breadcrumb }}</li>
        </ol>
      </nav>

      <div
        class="mt-8 grid items-center gap-10 lg:gap-14"
        :class="{ 'lg:grid-cols-[1.1fr_1fr]': art }"
      >
        <div :class="{ 'max-w-3xl': !art }">
          <p
            class="inline-flex items-center gap-2 rounded-full bg-(--art)/18 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-foreground"
          >
            <span class="size-1.5 rounded-full bg-(--art)" aria-hidden="true" />
            {{ eyebrow }}
          </p>
          <h1
            data-testid="page-heading"
            class="mt-4 text-balance text-3xl font-bold tracking-tight sm:text-4xl"
          >
            {{ title }}
          </h1>
          <p class="mt-4 text-pretty text-base leading-relaxed text-muted-foreground sm:text-lg">
            {{ lede }}
          </p>

          <div v-if="!hideActions" class="mt-8 flex flex-col gap-3 sm:flex-row">
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
          <p v-if="sandboxStore.enabled && !hideActions" class="mt-3 text-sm text-muted-foreground">
            {{ t('sandbox.cta.note') }}
          </p>
        </div>

        <div v-if="art" data-testid="content-header-media">
          <PageArt :kind="art" />
        </div>
      </div>
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
