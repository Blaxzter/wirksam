<script setup lang="ts">
/**
 * The top of a shared list's public page: the event and its days, the list's
 * title and its intro.
 *
 * Title and intro are organiser text on a page that strangers trust, so both
 * are plain interpolation. The intro keeps its line breaks and nothing else:
 * no HTML, no Markdown, no links made clickable (`lib/markdown.ts` is for
 * location descriptions only). An address written into it stays text.
 */
import { computed, useTemplateRef } from 'vue'

import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import type { PublicSharedList } from '@/client/types.gen'

const props = withDefaults(
  defineProps<{
    list: PublicSharedList
    /** `p` where the header is a picture of the page inside another one (the preview). */
    headingTag?: 'h1' | 'p'
  }>(),
  { headingTag: 'h1' },
)

const { t } = useI18n()
const { formatDaySpan } = useFormatters()
const title = useTemplateRef<HTMLElement>('title')

const eventLine = computed(() =>
  t('guestSignup.page.eventLine', {
    event: props.list.event.name,
    days: formatDaySpan(props.list.event.start_date, props.list.event.end_date),
  }),
)

/** Where the page puts focus when it returns to the list. */
function focus(): void {
  title.value?.focus({ preventScroll: true })
}

defineExpose({ focus })
</script>

<template>
  <header class="space-y-2 rounded-2xl bg-hero p-5 text-hero-foreground sm:p-6">
    <p class="text-sm font-semibold text-hero-foreground/85" data-testid="shared-list-event">
      {{ eventLine }}
    </p>
    <component
      :is="headingTag"
      ref="title"
      :data-testid="headingTag === 'h1' ? 'page-heading' : undefined"
      :tabindex="headingTag === 'h1' ? -1 : undefined"
      class="text-2xl leading-tight font-bold tracking-tight break-words focus:outline-none"
    >
      {{ list.title }}
    </component>
    <p
      v-if="list.intro"
      class="text-sm leading-relaxed break-words whitespace-pre-line"
      data-testid="shared-list-intro"
    >
      {{ list.intro }}
    </p>
  </header>
</template>
