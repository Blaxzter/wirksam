<script setup lang="ts">
/**
 * The pitch beside the auth forms — and, below `lg`, a slim branded band.
 *
 * A visual sibling of `SelectEventHeroPane`: same `--hero` surface, same
 * `--hero-speck` glows, same inverted logo, same proof-point tiles. It is
 * deliberately *not* a verbal sibling — `duties.selectEvent.visual.*` is still
 * written in the older formal register, and everything under `auth.` is "du".
 *
 * Two things the sibling does not do. The glows are separate layers here and
 * drift, slowly enough to be felt rather than watched; and the copy arrives
 * rather than appearing, staggered down the pane.
 *
 * On a phone all of that collapses to a 56px band with the wordmark in it. A
 * headline, a subhead and three tiles is some 320px of argument stacked on top
 * of the first input, and the person on this screen has already decided — they
 * came here to sign in, not to be sold to.
 */
import { computed } from 'vue'

import {
  BellRing,
  CalendarCheck,
  CalendarPlus,
  HandHeart,
  Inbox,
  LockKeyhole,
  Megaphone,
  ShieldCheck,
  Ticket,
  Users,
} from '@lucide/vue'
import type { LucideIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import wirksamLightLogo from '@/assets/logo/wirksam-light.svg'

import { isSwitchOn, useAppConfig } from '@/composables/useAppConfig'

import AuthShiftMotif from '@/components/auth/AuthShiftMotif.vue'

/** One per auth screen. Names match the `auth.*` locale keys they read. */
export type AuthHeroVariant =
  | 'login'
  | 'register'
  | 'forgotPassword'
  | 'resetPassword'
  | 'verifyEmail'

const props = withDefaults(
  defineProps<{
    variant?: AuthHeroVariant
    /**
     * Swap the headline for the variant's `problemHeadline`, where it has one.
     * A dead verification link is not a moment to open with "now we can reach
     * you".
     */
    problem?: boolean
  }>(),
  { variant: 'login', problem: false },
)

const { t, te } = useI18n()

/**
 * The order the points are read in, and the icon for each.
 *
 * Here rather than in the locale files because the pre-commit hook sorts those
 * alphabetically — `Object.entries` over the JSON would hand back whatever the
 * alphabet decided, which is not an argument.
 */
const POINTS: Record<AuthHeroVariant, readonly (readonly [string, LucideIcon])[]> = {
  login: [
    ['shifts', CalendarCheck],
    ['reminders', BellRing],
    ['team', Users],
  ],
  register: [
    ['invite', Ticket],
    ['own', CalendarPlus],
    ['free', HandHeart],
  ],
  forgotPassword: [
    ['link', Inbox],
    ['safe', ShieldCheck],
  ],
  resetPassword: [
    ['length', LockKeyhole],
    ['devices', ShieldCheck],
  ],
  verifyEmail: [
    ['reminders', BellRing],
    ['changes', Megaphone],
    ['control', ShieldCheck],
  ],
}

/**
 * Always the light wordmark, with no `useColorMode()` in sight.
 *
 * `--hero` is a dark saturated green in *both* themes — `oklch(0.40 …)` in
 * light and `oklch(0.30 …)` in dark — so the surface under the logo never gets
 * light enough for the dark-ink variant to be legible on it. Switching the
 * asset by colour mode, as the select-event pane does, paints near-black ink on
 * dark green the moment the app is in dark mode.
 */
const visualLogo = wirksamLightLogo

/**
 * The wordmark leads back to the landing page, as it does everywhere else.
 * Without one, `/` redirects straight back here, so it stays a plain image.
 */
const landingEnabled = isSwitchOn(useAppConfig().LANDING_ENABLED)

const points = computed(() => POINTS[props.variant])

/**
 * `problemHeadline` is an optional per-variant override, so a screen with two
 * moods (verify-email, which is also the dead-link screen) can change its tune
 * without every other variant having to declare a second headline it never uses.
 */
const headline = computed(() => {
  const base = `auth.${props.variant}.visual`
  const problemKey = `${base}.problemHeadline`
  return props.problem && te(problemKey) ? t(problemKey) : t(`${base}.headline`)
})

const subhead = computed(() => t(`auth.${props.variant}.visual.subhead`))

/**
 * The motif is the product's own metaphor, so it only belongs on the two
 * screens that are actually about joining in. On a password-recovery screen it
 * would be decoration for its own sake.
 */
const showMotif = computed(() => props.variant === 'login' || props.variant === 'register')
</script>

<template>
  <aside
    data-hero-motion
    class="relative isolate shrink-0 overflow-hidden bg-hero text-hero-foreground lg:flex lg:min-h-0 lg:flex-col"
  >
    <!-- Decoration. Two drifting glows, each inset well past the pane so the
         drift never walks an edge into view, and one pass of light on arrival.
         `will-change` is behind `motion-safe:` so a reduced-motion visitor is
         not charged two composited layers for nothing.

         Desktop only. The blobs are sized for a full-height pane, and slicing
         them through the 56px mobile band shows a corner of each rather than
         the whole shape — which reads as a smear across the wordmark instead of
         as light. The band is flat `--hero` there, which is what it should be. -->
    <div
      aria-hidden="true"
      class="pointer-events-none absolute inset-0 -z-10 hidden overflow-hidden lg:block"
    >
      <div
        class="absolute -inset-[20%] animate-hero-drift-a motion-safe:[will-change:transform] motion-reduce:animate-none"
        style="
          background: radial-gradient(
            ellipse 45% 42% at 24% 20%,
            color-mix(in oklab, var(--hero-speck) var(--hero-speck-opacity), transparent) 0%,
            transparent 62%
          );
        "
      />
      <div
        class="absolute -inset-[20%] animate-hero-drift-b motion-safe:[will-change:transform] motion-reduce:animate-none"
        style="
          background: radial-gradient(
            ellipse 52% 46% at 78% 86%,
            color-mix(in oklab, var(--hero-speck) var(--hero-speck-opacity), transparent) 0%,
            transparent 66%
          );
        "
      />
      <!-- `motion-safe:` rather than `motion-reduce:animate-none`: with no
           animation at all the `both` fill mode would park a bright bar at the
           left edge and leave it there. -->
      <div
        class="absolute -inset-y-1/3 left-0 w-1/4 opacity-0 motion-safe:animate-hero-sheen"
        style="
          background: linear-gradient(
            90deg,
            transparent,
            color-mix(in oklab, var(--hero-foreground) 8%, transparent),
            transparent
          );
        "
      />
    </div>

    <!-- MOBILE: the whole pane. Real content rather than `aria-hidden`, since
         it is the only place the product is named on this screen. -->
    <div class="flex items-center gap-3 px-5 py-3.5 sm:px-8 lg:hidden">
      <component
        :is="landingEnabled ? 'RouterLink' : 'span'"
        :to="landingEnabled ? { name: 'landing' } : undefined"
        data-testid="link-logo-home"
        class="inline-flex rounded-sm focus-visible:ring-2 focus-visible:ring-hero-foreground focus-visible:outline-none"
      >
        <img :src="visualLogo" alt="WirkSam" class="h-6 w-auto shrink-0" />
      </component>
    </div>

    <!-- DESKTOP: hidden from assistive tech. Every word of it is a pitch, and a
         screen reader should land on the heading of the form rather than on
         sixty words of argument first. It is also why the form comes first in
         DOM order and this pane is placed with `lg:order-first`. -->
    <!--
      `tabindex="-1"` is load-bearing, not decoration. Since Chrome 127, a
      scroll container that actually overflows and holds nothing focusable is
      added to the sequential focus order by the browser so it can be scrolled
      with the arrow keys — no `tabindex` attribute involved. This pane
      overflows on an ordinary laptop (it fits at 1440x900 but not at 1280x720),
      so without this a Tab past the footer would land focus inside an
      `aria-hidden` subtree: a big focus ring around the marketing column and a
      silent stop for anyone using a screen reader. `-1` keeps it scrollable by
      wheel and pointer while taking it back out of the tab sequence.
    -->
    <div
      aria-hidden="true"
      tabindex="-1"
      class="hidden min-h-0 flex-1 flex-col overflow-x-hidden overflow-y-auto p-8 outline-none lg:flex xl:p-12"
    >
      <!-- A pointer shortcut only: this subtree is `aria-hidden`, so the link
           must stay out of the tab order (`tabindex="-1"`). Keyboard and
           screen-reader users get the "back to home" link above the form. -->
      <component
        :is="landingEnabled ? 'RouterLink' : 'span'"
        :to="landingEnabled ? { name: 'landing' } : undefined"
        tabindex="-1"
        class="shrink-0 animate-auth-rise self-start motion-reduce:animate-none"
      >
        <img :src="visualLogo" alt="" class="h-9 w-auto" />
      </component>

      <!-- `my-auto` rather than a fixed top margin: on a tall window the block
           sits centred, and on a short one it simply stops centring instead of
           pushing the footnote out and raising a scrollbar down the middle of
           the screen. -->
      <div class="mx-auto my-auto w-full max-w-md py-4">
        <h2
          class="animate-auth-rise text-4xl leading-tight font-bold text-balance [animation-delay:80ms] motion-reduce:animate-none xl:text-5xl"
        >
          {{ headline }}
        </h2>

        <p
          class="mt-5 animate-auth-rise text-base leading-relaxed text-pretty text-hero-foreground/80 [animation-delay:160ms] motion-reduce:animate-none"
        >
          {{ subhead }}
        </p>

        <AuthShiftMotif
          v-if="showMotif"
          class="mt-8 animate-auth-rise [animation-delay:240ms] motion-reduce:animate-none"
        />

        <ul class="mt-7 space-y-2.5">
          <li
            v-for="([key, icon], index) in points"
            :key="key"
            class="flex animate-auth-rise items-start gap-3 rounded-xl bg-hero-foreground/10 p-4 motion-reduce:animate-none"
            :style="{ animationDelay: `${320 + index * 80}ms` }"
          >
            <component :is="icon" class="mt-0.5 size-5 shrink-0" />
            <div class="text-sm">
              <p class="font-semibold">
                {{ t(`auth.${variant}.visual.points.${key}.title`) }}
              </p>
              <!-- `/80` is the floor for body copy on this surface: it measures
                   5.8:1 against `--hero` in light mode, where the axe scan runs.
                   `/60` drops to 4.05 and fails AA. -->
              <p class="text-hero-foreground/80">
                {{ t(`auth.${variant}.visual.points.${key}.body`) }}
              </p>
            </div>
          </li>
        </ul>
      </div>

      <p
        class="shrink-0 animate-auth-rise text-xs text-hero-foreground/70 [animation-delay:620ms] motion-reduce:animate-none"
      >
        {{ t('auth.visual.footer') }}
      </p>
    </div>
  </aside>
</template>
