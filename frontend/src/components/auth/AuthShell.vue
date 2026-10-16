<script setup lang="ts">
/**
 * The frame every public auth screen sits in.
 *
 * Two columns from `lg`: the pitch on `--hero`, and the form on the page
 * background with nothing drawn around it. The card is gone on purpose — a card
 * says "this is one thing among several on a page", and there is nothing else
 * on this page. Bare, with room around it, the form *is* the screen.
 *
 * The form comes first in DOM order and the hero is placed with
 * `lg:order-first`. That is not a style preference: the E2E suite asserts that
 * exactly one Tab press separates the email field from the password field, and
 * that at most fifteen stops precede the email field. Ordering the DOM
 * form-first means the pane can grow as many links as it likes without ever
 * costing a tab stop. It also keeps the `<h1>` ahead of the pane's `<h2>`, so
 * heading order reads correctly.
 *
 * The legal links and the language and appearance controls live here rather
 * than in each view: these screens sit outside the pre-auth shell that normally
 * carries them, and somebody who cannot read "Passwort vergessen?" has to be
 * able to change the language *before* signing in.
 *
 * The one way out that is not part of the flow is "back to home", above the
 * badge (and the wordmark in the hero pane goes to the same place). It is the
 * first tab stop on the page, which the "at most fifteen" budget absorbs. With
 * the landing page switched off, `/` would only bounce back to sign-in, so the
 * link is not drawn at all.
 */
import type { Component } from 'vue'

import { ArrowLeftIcon } from '@lucide/vue'

import { isSwitchOn, useAppConfig } from '@/composables/useAppConfig'

import AuthHeroPane, { type AuthHeroVariant } from '@/components/auth/AuthHeroPane.vue'
import AuthShellFooter from '@/components/auth/AuthShellFooter.vue'

withDefaults(
  defineProps<{
    /** The `<h1>`. Bind a computed where the screen has several states. */
    title: string
    /** One supporting sentence under the heading. */
    description?: string
    /**
     * Marks the description for E2E. It is the element that used to be
     * `CardDescription`, and on the forgot-password screen its exact text is a
     * contract: the spec compares a known and an unknown address for
     * byte-identical wording, so the whole sentence has to live on one element.
     */
    descriptionTestid?: string
    /** Lucide icon for the badge above the heading. Omit for no badge. */
    icon?: Component
    /** Which pitch the hero pane tells. Defaults to the screen's own name. */
    hero?: AuthHeroVariant
    /** Show the hero's alternative headline — a dead link, a failed check. */
    heroProblem?: boolean
    /** `destructive` recolours the badge to match. */
    tone?: 'primary' | 'destructive'
    /** Spins the badge icon, for the one state that has no content yet. */
    busy?: boolean
  }>(),
  { hero: 'login', heroProblem: false, tone: 'primary', busy: false },
)

defineSlots<{
  /** The form, and whatever belongs with it. */
  default: () => unknown
  /** "Already have an account?" and friends, under a hairline rule. */
  footer?: () => unknown
}>()

const landingEnabled = isSwitchOn(useAppConfig().LANDING_ENABLED)
</script>

<template>
  <!--
    `min-h-svh` rather than `min-h-screen`: `100vh` on a phone resolves to the
    height with the browser toolbar *retracted*, so the form starts a toolbar's
    worth below the fold and a centred column sits visibly low. `svh` is the
    small viewport — constant for the session, and a `min-` so nothing clips.
    On `lg` there is no dynamic toolbar, so the two-pane frame is a fixed
    `h-dvh` and each column owns its own scroll.
  -->
  <div class="flex min-h-svh flex-col lg:grid lg:h-dvh lg:grid-cols-2 lg:overflow-hidden">
    <!-- `min-h-0` is what lets this column scroll instead of stretching the
         grid row past the viewport; without it `overflow-y-auto` never engages
         and the whole page scrolls behind a fixed pane. -->
    <main class="order-last flex flex-1 flex-col lg:order-none lg:min-h-0 lg:overflow-y-auto">
      <div class="flex flex-1 items-center justify-center px-5 py-10 sm:px-8 sm:py-14">
        <div class="w-full max-w-sm">
          <RouterLink
            v-if="landingEnabled"
            :to="{ name: 'landing' }"
            data-testid="link-back-home"
            class="-ml-1 mb-6 inline-flex items-center gap-1.5 rounded-sm px-1 py-1 text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            <ArrowLeftIcon class="size-4" aria-hidden="true" />
            {{ $t('auth.backToHome') }}
          </RouterLink>

          <div class="mb-8 animate-auth-rise motion-reduce:animate-none">
            <span
              v-if="icon"
              aria-hidden="true"
              class="mb-5 inline-flex size-11 items-center justify-center rounded-xl ring-1 ring-inset"
              :class="
                tone === 'destructive'
                  ? 'bg-destructive/10 text-destructive ring-destructive/20'
                  : 'bg-primary/10 text-primary ring-primary/15'
              "
            >
              <component :is="icon" class="size-5" :class="busy ? 'animate-spin' : ''" />
            </span>

            <h1
              data-testid="page-heading"
              class="text-2xl font-bold tracking-tight text-balance sm:text-3xl"
            >
              {{ title }}
            </h1>

            <p
              v-if="description"
              :data-testid="descriptionTestid"
              class="mt-2 text-sm leading-relaxed text-pretty text-muted-foreground"
            >
              {{ description }}
            </p>
          </div>

          <!-- Transform only, never opacity: the axe scan runs `color-contrast`
               at zero tolerance on three of these screens, and text caught
               mid-fade measures as a contrast failure. -->
          <div class="animate-auth-rise [animation-delay:70ms] motion-reduce:animate-none">
            <slot />
          </div>

          <div
            v-if="$slots.footer"
            class="mt-8 animate-auth-rise border-t pt-6 text-center text-sm text-muted-foreground [animation-delay:140ms] motion-reduce:animate-none"
          >
            <slot name="footer" />
          </div>
        </div>
      </div>

      <AuthShellFooter />
    </main>

    <AuthHeroPane class="lg:order-first" :variant="hero" :problem="heroProblem" />
  </div>
</template>
