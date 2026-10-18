<script setup lang="ts">
import { computed } from 'vue'

import { ArrowRightIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import LandingSection from '@/components/landing/LandingSection.vue'

import { relatedPages } from '@/lib/content-pages'

/**
 * Links from one content page to the others and back to the landing page.
 * Real links rather than buttons, so crawlers follow them from the
 * prerendered HTML.
 */
const { t } = useI18n()
const route = useRoute()

const pages = computed(() => relatedPages(route.name))
</script>

<template>
  <LandingSection id="related">
    <h2 class="text-center text-2xl font-bold tracking-tight">
      {{ t('preauth.content.related.title') }}
    </h2>
    <ul class="mx-auto mt-8 grid max-w-3xl gap-4 sm:grid-cols-2">
      <li v-for="page in pages" :key="page.routeName">
        <RouterLink
          :to="{ name: page.routeName }"
          :data-testid="`related-${page.key}`"
          class="group flex h-full flex-col rounded-2xl border bg-card p-5 shadow-sm transition-shadow hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <span class="flex items-center justify-between gap-3 font-semibold">
            {{ t(`preauth.content.related.pages.${page.key}.title`) }}
            <ArrowRightIcon
              class="size-4 shrink-0 text-primary transition-transform group-hover:translate-x-0.5"
              aria-hidden="true"
            />
          </span>
          <span class="mt-2 text-sm leading-relaxed text-muted-foreground">
            {{ t(`preauth.content.related.pages.${page.key}.description`) }}
          </span>
        </RouterLink>
      </li>
    </ul>
  </LandingSection>
</template>
