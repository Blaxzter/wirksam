<script setup lang="ts">
import { computed, ref } from 'vue'

import {
  CalendarClockIcon,
  ChartNoAxesColumnIcon,
  CheckIcon,
  GlobeIcon,
  LanguagesIcon,
  RssIcon,
  UsersIcon,
} from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import type { ScreenshotItem } from '@/composables/useScreenshotSource'

import { getTranslationList } from '@/lib/utils'

import LandingSection from './LandingSection.vue'
import ScreenshotFrame from './ScreenshotFrame.vue'
import ScreenshotLightbox from './ScreenshotLightbox.vue'
import SectionHeading from './SectionHeading.vue'

const { t } = useI18n()

/** Every name here needs a `-light` and `-dark` capture in both locales. */
const rows = [
  { key: 'shifts', screenshot: 'shift-schedule' },
  { key: 'overview', screenshot: 'tasks' },
  { key: 'bookings', screenshot: 'my-bookings' },
  { key: 'reminders', screenshot: 'notification-preferences' },
  // Appended, not inserted: e2e/tests/public/landing.spec.ts names the first
  // two gallery frames by file, so an earlier position breaks that spec.
  { key: 'clone', screenshot: 'clone-event' },
] as const

const extras = [
  { key: 'people', icon: UsersIcon },
  { key: 'availability', icon: CalendarClockIcon },
  { key: 'calendarFeed', icon: RssIcon },
  { key: 'reports', icon: ChartNoAxesColumnIcon },
  { key: 'discover', icon: GlobeIcon },
  { key: 'languages', icon: LanguagesIcon },
] as const

function bullets(key: string): string[] {
  return getTranslationList(t, `preauth.landing.features.rows.${key}.points`)
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
</script>

<template>
  <LandingSection id="features" tone="tinted" width="wide">
    <SectionHeading
      :eyebrow="t('preauth.landing.features.eyebrow')"
      :title="t('preauth.landing.features.title')"
      :lede="t('preauth.landing.features.lede')"
    />

    <div class="mt-14 space-y-16 sm:space-y-24">
      <div
        v-for="(row, index) in rows"
        :key="row.key"
        class="grid items-center gap-8 lg:grid-cols-2 lg:gap-12"
      >
        <div :class="index % 2 === 1 ? 'lg:order-2' : ''">
          <h3 class="text-2xl font-semibold tracking-tight">
            {{ t(`preauth.landing.features.rows.${row.key}.title`) }}
          </h3>
          <p class="mt-3 text-pretty leading-relaxed text-muted-foreground">
            {{ t(`preauth.landing.features.rows.${row.key}.description`) }}
          </p>
          <ul class="mt-5 space-y-2.5">
            <li v-for="point in bullets(row.key)" :key="point" class="flex gap-3">
              <CheckIcon class="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
              <span class="text-sm leading-relaxed">{{ point }}</span>
            </li>
          </ul>
        </div>

        <ScreenshotFrame
          :name="row.screenshot"
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
      <!-- A plain list, not a <dl>: a description list may not nest its <dt>/<dd>
           inside a second wrapper, which the icon-beside-text layout needs. -->
      <ul class="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        <li v-for="extra in extras" :key="extra.key" class="flex gap-4">
          <span
            class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10"
            aria-hidden="true"
          >
            <component :is="extra.icon" class="size-5 text-primary" />
          </span>
          <div>
            <h4 class="font-semibold">
              {{ t(`preauth.landing.features.more.items.${extra.key}.title`) }}
            </h4>
            <p class="mt-1 text-sm leading-relaxed text-muted-foreground">
              {{ t(`preauth.landing.features.more.items.${extra.key}.description`) }}
            </p>
          </div>
        </li>
      </ul>
    </div>
    <ScreenshotLightbox v-model:index="zoomed" :items="gallery" />
  </LandingSection>
</template>
