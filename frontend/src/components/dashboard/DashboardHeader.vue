<script setup lang="ts">
/**
 * The top of the dashboard: a greeting, today's date and, during the event,
 * which day of it this is.
 *
 * It replaced a heading that said "Dashboard" and a sentence explaining what
 * a dashboard is. Neither told anyone anything; "Saturday, July 18 · Day 2 of
 * 3" is the one line of context somebody arriving at a festival actually
 * wants. It needs no feed, so it renders at once, before the cards below it
 * have loaded.
 *
 * "Find a shift" sits here on desktop only: on a phone the empty next-shift
 * card and the open-shifts list already end in that same offer, and a fourth
 * button in a 390 px header would push the greeting onto two lines.
 */
import { computed } from 'vue'

import { Search } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import { Button } from '@/components/ui/button'

import { OPEN_SHIFTS_ROUTE, greetingBucket, localIsoDate } from '@/lib/dashboard'

const props = defineProps<{
  now: Date
  /** `greetingName(profile)`: null greets without a name. */
  name: string | null
  eventDay: { day: number; total: number } | null
  /** False in an event that is over, where there is nothing left to find. */
  showFindShift: boolean
}>()

const { t } = useI18n()
const { formatDateLabel } = useFormatters()

const longDate = computed(() =>
  formatDateLabel(localIsoDate(props.now), { weekday: 'long', day: 'numeric', month: 'long' }),
)

const greeting = computed(() => {
  const plain = t(`dashboard.home.greeting.${greetingBucket(props.now)}`)
  return props.name
    ? t('dashboard.home.greeting.withName', { greeting: plain, name: props.name })
    : plain
})
</script>

<template>
  <header data-testid="dashboard-header" class="flex flex-wrap items-end justify-between gap-4">
    <div class="min-w-0">
      <p class="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
        <span>{{ longDate }}</span>
        <span
          v-if="eventDay"
          data-testid="dashboard-event-day"
          class="rounded-full bg-secondary px-2 py-px text-xs font-semibold text-secondary-foreground"
        >
          {{ t('dashboard.home.dayOfEvent', { day: eventDay.day, total: eventDay.total }) }}
        </span>
      </p>
      <h1
        data-testid="page-heading"
        class="mt-0.5 text-[1.625rem] leading-tight font-bold tracking-[-0.01em] @4xl:mt-1 @4xl:text-[2rem] @4xl:tracking-[-0.015em]"
      >
        {{ greeting }}
      </h1>
    </div>
    <Button
      v-if="showFindShift"
      as-child
      variant="outline"
      class="hidden h-11 rounded-xl px-4 font-semibold has-[>svg]:px-4 @4xl:inline-flex"
    >
      <RouterLink data-testid="btn-header-find-shift" :to="OPEN_SHIFTS_ROUTE">
        <Search aria-hidden="true" />
        {{ t('dashboard.home.findShift') }}
      </RouterLink>
    </Button>
  </header>
</template>
