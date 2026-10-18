<script setup lang="ts">
import { SparklesIcon } from '@lucide/vue'
import { siGithub } from 'simple-icons'

import { isSwitchOn, useAppConfig } from '@/composables/useAppConfig'

import SimpleIcon from '@/components/utils/SimpleIcon.vue'

import { formatDate } from '@/lib/format'
import { REPO_URL } from '@/lib/project-links'

const appVersion = __APP_VERSION__
const appVersionDate = __APP_VERSION_DATE__

/**
 * The content pages, linked from every public page so crawlers find them. They
 * exist only alongside the landing page (`requires` in lib/seo.ts).
 */
const content = isSwitchOn(useAppConfig().LANDING_ENABLED)
  ? ([
      { name: 'alternatives', label: 'preauth.layout.footer.alternatives' },
      { name: 'use-case-club-festival', label: 'preauth.layout.footer.clubFestival' },
    ] as const)
  : []

const legal = [
  { name: 'privacy', label: 'preauth.layout.footer.privacy' },
  { name: 'terms', label: 'preauth.layout.footer.terms' },
  { name: 'impressum', label: 'preauth.layout.footer.impressum' },
] as const

const links = [...content, ...legal]
</script>

<template>
  <footer class="mt-auto shrink-0 border-t">
    <!-- `max-w-6xl` and the same gutters as the header, so the footer lines up
         with everything above it instead of running wider. -->
    <div
      class="mx-auto flex w-full max-w-6xl flex-col items-center gap-5 px-4 py-8 text-sm text-muted-foreground sm:flex-row sm:items-start sm:justify-between sm:gap-6 sm:px-6"
    >
      <div class="flex flex-col items-center gap-1.5 sm:items-start">
        <p>{{ $t('preauth.layout.footer.copyright') }}</p>
        <RouterLink
          :to="{ name: 'preauth-changelog' }"
          class="inline-flex items-center gap-1 text-xs transition-colors hover:text-foreground"
        >
          <SparklesIcon class="size-3 shrink-0" />
          <span>
            {{
              $t('preauth.layout.footer.version', {
                version: appVersion,
                date: formatDate(appVersionDate),
              })
            }}
          </span>
        </RouterLink>
      </div>

      <!-- Wrapping, not one row: "Nutzungsbedingungen" alone is half a phone
           wide, and the three of them used to overrun the gutter entirely. -->
      <nav class="flex flex-wrap items-center justify-center gap-x-4 gap-y-2 sm:justify-end">
        <RouterLink
          v-for="item in links"
          :key="item.name"
          :to="{ name: item.name }"
          class="transition-colors hover:text-foreground"
        >
          {{ $t(item.label) }}
        </RouterLink>
        <a
          :href="REPO_URL"
          target="_blank"
          rel="noopener"
          class="inline-flex items-center gap-1.5 transition-colors hover:text-foreground"
        >
          <SimpleIcon :icon-data="siGithub" class-name="size-3.5" />
          {{ $t('preauth.layout.footer.github') }}
        </a>
      </nav>
    </div>
  </footer>
</template>
