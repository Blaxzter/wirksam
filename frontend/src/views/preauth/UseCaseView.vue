<script setup lang="ts">
import { computed, ref } from 'vue'

import { useI18n } from 'vue-i18n'

import type { ScreenshotItem } from '@/composables/useScreenshotSource'

import ContentPageShell from '@/components/content/ContentPageShell.vue'
import ContentRelated from '@/components/content/ContentRelated.vue'
import LandingFaq from '@/components/landing/LandingFaq.vue'
import LandingSection from '@/components/landing/LandingSection.vue'
import ScreenshotFrame from '@/components/landing/ScreenshotFrame.vue'
import ScreenshotLightbox from '@/components/landing/ScreenshotLightbox.vue'
import SectionHeading from '@/components/landing/SectionHeading.vue'

import { USE_CASES, type UseCaseKey } from '@/lib/content-pages'

/**
 * One page per kind of event (club festival, …), all with the same shape: the
 * answer up front, the usual problems, a worked example step by step with
 * screenshots, and an FAQ that the prerender mirrors into FAQPage JSON-LD.
 *
 * The route passes `useCase`; the order of things comes from
 * `USE_CASES` in lib/content-pages.ts and every word from
 * `preauth.useCases.<useCase>`. A new page is mostly copy.
 */
const props = defineProps<{ useCase: UseCaseKey }>()

const { t } = useI18n()

const config = computed(() => USE_CASES[props.useCase])
const base = computed(() => `preauth.useCases.${props.useCase}`)

const gallery = computed<ScreenshotItem[]>(() =>
  config.value.steps.map((step) => ({
    name: step.screenshot,
    alt: t(`${base.value}.steps.items.${step.key}.screenshotAlt`),
    caption: t(`${base.value}.steps.items.${step.key}.title`),
  })),
)

const zoomed = ref<number | null>(null)
</script>

<template>
  <ContentPageShell
    :eyebrow="t(`${base}.hero.eyebrow`)"
    :title="t(`${base}.hero.title`)"
    :lede="t(`${base}.hero.lede`)"
    :breadcrumb="t(`${base}.breadcrumb`)"
    :cta-title="t(`${base}.ctaTitle`)"
  >
    <LandingSection id="problems">
      <SectionHeading
        :eyebrow="t(`${base}.pains.eyebrow`)"
        :title="t(`${base}.pains.title`)"
        :lede="t(`${base}.pains.lede`)"
      />
      <ul class="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <li
          v-for="pain in config.pains"
          :key="pain"
          class="rounded-2xl border bg-card p-5 shadow-sm"
        >
          <h3 class="font-semibold">{{ t(`${base}.pains.items.${pain}.title`) }}</h3>
          <p class="mt-2 text-pretty text-sm leading-relaxed text-muted-foreground">
            {{ t(`${base}.pains.items.${pain}.description`) }}
          </p>
        </li>
      </ul>
    </LandingSection>

    <LandingSection id="how-it-works" tone="tinted" width="wide">
      <SectionHeading
        :eyebrow="t(`${base}.steps.eyebrow`)"
        :title="t(`${base}.steps.title`)"
        :lede="t(`${base}.steps.lede`)"
      />

      <!-- An ordered list: the numbers carry meaning, and screen readers say so. -->
      <ol class="mt-14 space-y-16 sm:space-y-20">
        <li
          v-for="(step, index) in config.steps"
          :key="step.key"
          class="grid items-center gap-8 lg:grid-cols-2 lg:gap-12"
        >
          <div :class="index % 2 === 1 ? 'lg:order-2' : ''">
            <span
              class="flex size-9 items-center justify-center rounded-full bg-primary text-sm font-bold text-primary-foreground"
              aria-hidden="true"
            >
              {{ index + 1 }}
            </span>
            <h3 class="mt-4 text-2xl font-semibold tracking-tight">
              {{ t(`${base}.steps.items.${step.key}.title`) }}
            </h3>
            <p class="mt-3 text-pretty leading-relaxed text-muted-foreground">
              {{ t(`${base}.steps.items.${step.key}.description`) }}
            </p>
          </div>

          <ScreenshotFrame
            :name="step.screenshot"
            :alt="t(`${base}.steps.items.${step.key}.screenshotAlt`)"
            :class="index % 2 === 1 ? 'lg:order-1' : ''"
            @zoom="zoomed = index"
          />
        </li>
      </ol>
      <ScreenshotLightbox v-model:index="zoomed" :items="gallery" />
    </LandingSection>

    <LandingFaq :base="`${base}.faq`" :keys="config.faq" />

    <ContentRelated />
  </ContentPageShell>
</template>
