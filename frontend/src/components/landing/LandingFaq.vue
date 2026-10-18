<script setup lang="ts">
import { computed } from 'vue'

import { ChevronDownIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { faqKeys } from '@/lib/seo'

import LandingSection from './LandingSection.vue'
import SectionHeading from './SectionHeading.vue'

const props = withDefaults(
  defineProps<{
    /** Landing page only: whether the demo question is shown. */
    demoEnabled?: boolean
    /**
     * Another page's FAQ: the i18n key holding `eyebrow`, `title`, `lede` and
     * `items`, and the item keys in display order (`PublicPage.faq` in seo.ts).
     */
    base?: string
    keys?: readonly string[]
  }>(),
  { demoEnabled: false, base: 'preauth.landing.faq', keys: undefined },
)

const { t } = useI18n()

/**
 * Native `<details>` rather than the accordion component on purpose: a closed
 * accordion panel is not in the DOM, so the answers would be missing from the
 * prerendered HTML that search engines and LLM crawlers read. Here every answer
 * is in the markup, and the build mirrors the same list into FAQPage JSON-LD.
 */
const items = computed(() => props.keys ?? faqKeys(props.demoEnabled))
</script>

<template>
  <LandingSection id="faq" tone="tinted">
    <SectionHeading
      :eyebrow="t(`${base}.eyebrow`)"
      :title="t(`${base}.title`)"
      :lede="t(`${base}.lede`)"
    />

    <div class="mx-auto mt-12 max-w-3xl divide-y rounded-2xl border bg-card shadow-sm">
      <details v-for="key in items" :key="key" :id="`faq-${key}`" class="group scroll-mt-36">
        <summary
          class="flex cursor-pointer list-none items-center justify-between gap-4 px-6 py-5 text-left font-semibold [&::-webkit-details-marker]:hidden"
        >
          <h3 class="text-base">{{ t(`${base}.items.${key}.question`) }}</h3>
          <ChevronDownIcon
            class="size-5 shrink-0 text-muted-foreground transition-transform group-open:rotate-180"
            aria-hidden="true"
          />
        </summary>
        <p class="text-pretty px-6 pb-6 leading-relaxed text-muted-foreground">
          {{ t(`${base}.items.${key}.answer`) }}
        </p>
      </details>
    </div>

    <slot />
  </LandingSection>
</template>
