<script setup lang="ts">
import { type Component, computed, ref } from 'vue'

import {
  ArrowRightIcon,
  CalendarClockIcon,
  ChartNoAxesColumnIcon,
  GlobeIcon,
  LanguagesIcon,
  RssIcon,
  ShieldCheckIcon,
  TicketIcon,
  UsersIcon,
  UsersRoundIcon,
} from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import type { ScreenshotFocus, ScreenshotItem } from '@/composables/useScreenshotSource'

import { type DocPage, docPageById, docRouteName } from '@/lib/content-pages'

import LandingSection from './LandingSection.vue'
import ScreenshotFrame from './ScreenshotFrame.vue'
import ScreenshotLightbox from './ScreenshotLightbox.vue'
import SectionHeading from './SectionHeading.vue'

const { t } = useI18n()

/**
 * Every name here needs a `-light` and `-dark` capture in both locales. `focus`
 * is the part of it the row shows: the whole app at this width is too small to
 * read. `doc` is the page that explains the row in full; the detail lives there,
 * so a row here is a heading, a sentence or two and the picture.
 */
const rows: readonly {
  key: string
  screenshot: string
  focus: ScreenshotFocus
  doc?: string
}[] = [
  {
    key: 'shifts',
    screenshot: 'shift-schedule',
    focus: { x: 0.31, y: 0.468, zoom: 1.8 },
    doc: 'feature/shift-planning',
  },
  { key: 'overview', screenshot: 'tasks', focus: { x: 0.19, y: 0.243, zoom: 1.85 } },
  // New rows go after these two: e2e/tests/public/landing.spec.ts names the
  // first two gallery frames by file, so an earlier position breaks that spec.
  {
    key: 'venue',
    screenshot: 'venue-map',
    focus: { x: 0.215, y: 0.135, zoom: 1.3 },
    doc: 'feature/venue-map',
  },
  {
    key: 'bookings',
    screenshot: 'my-bookings',
    focus: { x: 0.18, y: 0.05, zoom: 1.45 },
    doc: 'feature/booking',
  },
  {
    key: 'reminders',
    screenshot: 'notification-preferences',
    focus: { x: 0.23, y: 0.045, zoom: 1.38 },
    doc: 'feature/notifications',
  },
  {
    key: 'clone',
    screenshot: 'clone-event',
    focus: { x: 0.31, y: 0.225, zoom: 1.8 },
    doc: 'guide/next-year',
  },
]

/** The rest by name only, each a link to the page that covers it. */
const extras: readonly { key: string; icon: Component; doc?: string }[] = [
  { key: 'vouchers', icon: TicketIcon, doc: 'feature/vouchers' },
  { key: 'peopleInCharge', icon: ShieldCheckIcon, doc: 'feature/people-in-charge' },
  { key: 'teams', icon: UsersRoundIcon, doc: 'feature/teams' },
  { key: 'people', icon: UsersIcon, doc: 'feature/members' },
  { key: 'availability', icon: CalendarClockIcon, doc: 'feature/booking' },
  { key: 'calendarFeed', icon: RssIcon, doc: 'feature/booking' },
  { key: 'reports', icon: ChartNoAxesColumnIcon, doc: 'feature/hours-and-reports' },
  { key: 'discover', icon: GlobeIcon, doc: 'feature/members' },
  { key: 'languages', icon: LanguagesIcon },
]

function page(id: string | undefined): DocPage | undefined {
  return id ? docPageById(id) : undefined
}

/** The rows double as a gallery, so the viewer can page between them. */
const gallery = computed<ScreenshotItem[]>(() =>
  rows.map((row) => ({
    name: row.screenshot,
    alt: t(`preauth.landing.features.rows.${row.key}.screenshotAlt`),
    caption: t(`preauth.landing.features.rows.${row.key}.title`),
  })),
)

const zoomed = ref<number | null>(null)

const PILL =
  'inline-flex items-center gap-2 rounded-full border bg-card px-4 py-2 text-sm font-medium shadow-sm'
</script>

<template>
  <LandingSection id="features" tone="tinted" width="wide">
    <SectionHeading
      :eyebrow="t('preauth.landing.features.eyebrow')"
      :title="t('preauth.landing.features.title')"
      :lede="t('preauth.landing.features.lede')"
    />

    <div class="mt-14 space-y-14 sm:space-y-20">
      <div
        v-for="(row, index) in rows"
        :key="row.key"
        class="grid items-center gap-6 lg:gap-12"
        :class="index % 2 === 1 ? 'lg:grid-cols-[3fr_2fr]' : 'lg:grid-cols-[2fr_3fr]'"
      >
        <div :class="index % 2 === 1 ? 'lg:order-2' : ''">
          <h3 class="text-2xl font-semibold tracking-tight">
            {{ t(`preauth.landing.features.rows.${row.key}.title`) }}
          </h3>
          <p class="mt-3 text-pretty leading-relaxed text-muted-foreground">
            {{ t(`preauth.landing.features.rows.${row.key}.description`) }}
          </p>
          <RouterLink
            v-if="page(row.doc)"
            :to="{ name: docRouteName(page(row.doc)!) }"
            :data-testid="`landing-feature-link-${row.key}`"
            class="group mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-primary underline-offset-2 hover:underline"
          >
            {{ t(`preauth.docs.pages.${page(row.doc)!.key}.name`) }}
            <ArrowRightIcon
              class="size-4 transition-transform group-hover:translate-x-0.5"
              aria-hidden="true"
            />
          </RouterLink>
        </div>

        <ScreenshotFrame
          :name="row.screenshot"
          :focus="row.focus"
          :alt="t(`preauth.landing.features.rows.${row.key}.screenshotAlt`)"
          :class="index % 2 === 1 ? 'lg:order-1' : ''"
          @zoom="zoomed = index"
        />
      </div>
    </div>

    <div class="mt-20 border-t pt-12">
      <h3 class="text-center text-xl font-semibold">
        {{ t('preauth.landing.features.more.title') }}
      </h3>
      <ul class="mx-auto mt-6 flex max-w-4xl flex-wrap justify-center gap-2.5">
        <li v-for="extra in extras" :key="extra.key">
          <RouterLink
            v-if="page(extra.doc)"
            :to="{ name: docRouteName(page(extra.doc)!) }"
            :data-testid="`landing-extra-${extra.key}`"
            :class="PILL"
            class="transition-shadow hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >
            <component :is="extra.icon" class="size-4 text-primary" aria-hidden="true" />
            {{ t(`preauth.landing.features.more.items.${extra.key}.title`) }}
          </RouterLink>
          <span v-else :class="PILL">
            <component :is="extra.icon" class="size-4 text-primary" aria-hidden="true" />
            {{ t(`preauth.landing.features.more.items.${extra.key}.title`) }}
          </span>
        </li>
      </ul>

      <p class="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row sm:gap-6">
        <RouterLink
          :to="{ name: 'features' }"
          data-testid="landing-all-features"
          class="font-medium text-primary underline underline-offset-2"
        >
          {{ t('preauth.landing.features.allFeatures') }}
        </RouterLink>
        <RouterLink
          :to="{ name: 'guides' }"
          data-testid="landing-all-guides"
          class="font-medium text-primary underline underline-offset-2"
        >
          {{ t('preauth.landing.features.allGuides') }}
        </RouterLink>
      </p>
    </div>
    <ScreenshotLightbox v-model:index="zoomed" :items="gallery" />
  </LandingSection>
</template>
