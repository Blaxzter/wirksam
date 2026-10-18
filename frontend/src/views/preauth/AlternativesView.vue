<script setup lang="ts">
import { computed, ref } from 'vue'

import { ExternalLinkIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import type { ScreenshotItem } from '@/composables/useScreenshotSource'

import ComparisonTable from '@/components/content/ComparisonTable.vue'
import ContentPageShell from '@/components/content/ContentPageShell.vue'
import ContentRelated from '@/components/content/ContentRelated.vue'
import LandingSection from '@/components/landing/LandingSection.vue'
import ScreenshotFrame from '@/components/landing/ScreenshotFrame.vue'
import ScreenshotLightbox from '@/components/landing/ScreenshotLightbox.vue'
import SectionHeading from '@/components/landing/SectionHeading.vue'

import { COMPARED_TOOLS, COMPARISON_SCREENSHOTS } from '@/lib/content-pages'

/**
 * WirkSam next to the other ways of planning volunteers. The table does not
 * have to come out in WirkSam's favour: each tool gets a note on when it is the
 * better choice, WirkSam included, and the interface is shown in screenshots
 * rather than described. Every fact is dated (`table.asOf`) and sourced
 * (`COMPARED_TOOLS` in lib/content-pages.ts).
 */
const { t } = useI18n()

const A = 'preauth.alternatives'

/** Shown without the scheme, so a long help-centre URL still wraps sensibly. */
const linkLabel = (url: string) => url.replace(/^https?:\/\//, '').replace(/\/$/, '')

const gallery = computed<ScreenshotItem[]>(() =>
  COMPARISON_SCREENSHOTS.map((shot) => ({
    name: shot.screenshot,
    alt: t(`preauth.landing.features.rows.${shot.key}.screenshotAlt`),
    caption: t(`preauth.landing.features.rows.${shot.key}.title`),
  })),
)

const zoomed = ref<number | null>(null)
</script>

<template>
  <ContentPageShell
    :eyebrow="t(`${A}.hero.eyebrow`)"
    :title="t(`${A}.hero.title`)"
    :lede="t(`${A}.hero.lede`)"
    :breadcrumb="t(`${A}.breadcrumb`)"
  >
    <LandingSection id="comparison" width="full">
      <SectionHeading
        :eyebrow="t(`${A}.table.eyebrow`)"
        :title="t(`${A}.table.title`)"
        :lede="t(`${A}.table.lede`)"
      />
      <ComparisonTable class="mt-12" />
      <p class="mt-4 text-center text-sm text-muted-foreground" data-testid="comparison-as-of">
        {{ t(`${A}.table.asOf`) }}
      </p>
    </LandingSection>

    <LandingSection id="which-fits" tone="tinted" width="wide">
      <SectionHeading
        :eyebrow="t(`${A}.fit.eyebrow`)"
        :title="t(`${A}.fit.title`)"
        :lede="t(`${A}.fit.lede`)"
      />

      <ul class="mt-12 grid gap-6 md:grid-cols-2">
        <li
          v-for="tool in COMPARED_TOOLS"
          :id="`tool-${tool.key}`"
          :key="tool.key"
          class="flex scroll-mt-36 flex-col rounded-2xl border bg-card p-6 shadow-sm"
          :class="tool.key === 'wirksam' ? 'border-primary/40' : ''"
        >
          <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <h3 class="text-xl font-semibold">
              {{ t(`${A}.tools.${tool.key}.name`) }}
            </h3>
            <a
              :href="tool.url"
              target="_blank"
              rel="noopener"
              class="inline-flex items-center gap-1 text-sm text-primary hover:underline"
            >
              {{ linkLabel(tool.url) }}
              <ExternalLinkIcon class="size-3.5" aria-hidden="true" />
            </a>
          </div>
          <p class="mt-3 text-pretty leading-relaxed text-muted-foreground">
            {{ t(`${A}.tools.${tool.key}.summary`) }}
          </p>

          <h4 class="mt-5 text-sm font-semibold">{{ t(`${A}.fit.goodFitLabel`) }}</h4>
          <p class="mt-1 text-pretty text-sm leading-relaxed">
            {{ t(`${A}.tools.${tool.key}.goodFit`) }}
          </p>

          <h4 class="mt-4 text-sm font-semibold">{{ t(`${A}.fit.lessSuitedLabel`) }}</h4>
          <p class="mt-1 text-pretty text-sm leading-relaxed">
            {{ t(`${A}.tools.${tool.key}.lessSuited`) }}
          </p>

          <!-- Pushed to the bottom so the cards in a row line their sources up. -->
          <div class="mt-auto pt-5">
            <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {{ t(`${A}.fit.sourcesLabel`) }}
            </p>
            <ul class="mt-1.5 space-y-1 text-xs">
              <li v-for="source in tool.sources" :key="source" class="break-all">
                <a
                  :href="source"
                  target="_blank"
                  rel="noopener nofollow"
                  class="text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                >
                  {{ linkLabel(source) }}
                </a>
              </li>
            </ul>
          </div>
        </li>
      </ul>
    </LandingSection>

    <LandingSection id="screenshots" width="wide">
      <SectionHeading
        :eyebrow="t(`${A}.screenshots.eyebrow`)"
        :title="t(`${A}.screenshots.title`)"
        :lede="t(`${A}.screenshots.lede`)"
      />
      <ul class="mt-12 grid gap-8 md:grid-cols-3">
        <li v-for="(shot, index) in gallery" :key="shot.name">
          <ScreenshotFrame :name="shot.name" :alt="shot.alt" @zoom="zoomed = index" />
          <p class="mt-3 text-center text-sm font-medium">{{ shot.caption }}</p>
        </li>
      </ul>
      <ScreenshotLightbox v-model:index="zoomed" :items="gallery" />
    </LandingSection>

    <ContentRelated />
  </ContentPageShell>
</template>
