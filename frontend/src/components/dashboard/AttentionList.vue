<script setup lang="ts">
/**
 * The organiser's to-do list, and only theirs: a plain member never gets this
 * block at all, because the backend sends `attention: null` for them.
 *
 * Every line is a count that implies an action, so every line is a link, with
 * the count first in a tinted square: red for shifts nobody is on, amber for
 * shifts short of people, plain for requests and drafts that can wait. It
 * renders nothing when every count is zero: an empty "needs your attention"
 * panel trains people to stop reading it.
 *
 * The count is 20 px bold, which counts as large text. At 17 px the red and
 * amber numbers on their /10 tints came out just under 4.5:1 in the classic
 * palette and in dark mode; as large text they need 3:1, which every palette
 * clears.
 */
import { ChevronRight } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import type { RouteLocationRaw } from 'vue-router'

import { teamsPageLocation } from '@/composables/useTeams'

import {
  type AttentionItem,
  type AttentionKey,
  type AttentionTone,
  OPEN_SHIFTS_ROUTE,
  formatCount,
} from '@/lib/dashboard'

const props = defineProps<{
  /** `attentionItems(feed.attention)` */
  items: AttentionItem[]
  /** The event the counts are for; the team requests link to its Teams page. */
  eventId: string | null
}>()

const { t } = useI18n()

const TONE_CLASS: Record<AttentionTone, string> = {
  destructive: 'bg-destructive/10 text-destructive',
  // The ring keeps a warm tint from going brown on a dark ground (the same
  // idea as the chips in ShiftBoardConcept.vue).
  warning: 'bg-warning/10 text-warning ring-1 ring-warning/40 ring-inset',
  neutral: 'bg-muted text-foreground',
}

function linkFor(key: AttentionKey): RouteLocationRaw {
  switch (key) {
    case 'requests':
      return { name: 'my-events', query: { tab: 'requests' } }
    case 'team-requests':
      return teamsPageLocation(props.eventId)
    case 'drafts':
      return { name: 'tasks' }
    default:
      return OPEN_SHIFTS_ROUTE
  }
}

/** The count is in the square, so the label carries none of its own. */
function labelFor(item: AttentionItem): string {
  switch (item.key) {
    case 'empty':
      return t('dashboard.home.attention.emptyShifts', { days: item.days }, item.count)
    case 'short':
      return t('dashboard.home.attention.shortShifts', { days: item.days }, item.count)
    case 'requests':
      return t('dashboard.home.attention.joinRequests', item.count)
    case 'team-requests':
      return t('dashboard.home.attention.teamRequests', item.count)
    default:
      return t('dashboard.home.attention.draftTasks', item.count)
  }
}
</script>

<template>
  <section
    v-if="items.length > 0"
    data-testid="dashboard-attention"
    aria-labelledby="dashboard-attention-title"
    class="min-w-0 rounded-2xl border bg-card text-card-foreground @4xl:rounded-[22px] @4xl:px-1 @4xl:pt-1"
  >
    <div class="px-4 pt-3.5 pb-1 @4xl:pt-4">
      <h2 id="dashboard-attention-title" class="text-[17px] font-bold @4xl:text-lg">
        {{ t('dashboard.home.attention.title') }}
      </h2>
      <p class="mt-0.5 text-sm text-muted-foreground">
        {{ t('dashboard.home.attention.subtitle') }}
      </p>
    </div>
    <ul class="px-2 pt-1 pb-2">
      <li v-for="item in items" :key="item.key">
        <RouterLink
          :to="linkFor(item.key)"
          :data-testid="'attention-' + item.key"
          class="flex min-h-[52px] items-center gap-3 rounded-xl px-2 py-1.5 transition-colors hover:bg-accent/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          <span
            data-testid="attention-count"
            class="flex h-11 min-w-11 shrink-0 items-center justify-center rounded-xl px-2 text-xl font-bold tabular-nums"
            :class="TONE_CLASS[item.tone]"
          >
            {{ formatCount(item.count) }}
          </span>
          <!-- A real space, so the link reads "2 Shifts …" rather than "2Shifts …". -->
          {{ ' ' }}
          <span class="min-w-0 flex-1 text-sm leading-snug">{{ labelFor(item) }}</span>
          <ChevronRight class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        </RouterLink>
      </li>
    </ul>
  </section>
</template>
