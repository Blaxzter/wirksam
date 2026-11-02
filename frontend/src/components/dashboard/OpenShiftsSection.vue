<script setup lang="ts">
/**
 * Where the event is still short of people, as cards you can sign up from.
 *
 * The feed sends up to six. A desktop grid shows them all; a phone stacks the
 * first four, because six full cards would push everything else off the
 * screen, and the link under them says how many more the Tasks board holds.
 *
 * That link is one element for both breakpoints (under the cards on a phone,
 * beside the heading on desktop, by grid placement alone) with the two
 * "(n more)" counts swapped by class. Two links would mean two
 * `btn-browse-open-shifts`, and Playwright's strict mode refuses a test id
 * that matches twice, hidden or not.
 */
import { computed } from 'vue'

import { ArrowRight } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import OpenShiftCard from '@/components/dashboard/OpenShiftCard.vue'

import type { DashboardOpenShift } from '@/client'
import { MOBILE_OPEN_SHIFT_LIMIT, OPEN_SHIFTS_ROUTE, hiddenCount } from '@/lib/dashboard'

const props = defineProps<{
  /** feed.open_shifts (at most six) */
  shifts: DashboardOpenShift[]
  /** feed.open_shift_count */
  totalCount: number
  /** feed.open_places */
  openPlaces: number
  now: Date
  /** True only with no event in view, where the cards come from several events. */
  showEventName: boolean
}>()

const emit = defineEmits<{ select: [shiftId: string] }>()

const { t } = useI18n()

const hiddenMobile = computed(() =>
  hiddenCount(props.totalCount, Math.min(props.shifts.length, MOBILE_OPEN_SHIFT_LIMIT)),
)
const hiddenDesktop = computed(() => hiddenCount(props.totalCount, props.shifts.length))
</script>

<template>
  <section
    data-testid="dashboard-open-shifts"
    aria-labelledby="dashboard-open-title"
    class="grid min-w-0 gap-y-2.5 @4xl:grid-cols-[minmax(0,1fr)_auto] @4xl:items-end @4xl:gap-x-4 @4xl:gap-y-3.5"
  >
    <div class="min-w-0">
      <h2 id="dashboard-open-title" class="text-[17px] font-bold @4xl:text-lg">
        {{ t('dashboard.home.open.title') }}
      </h2>
      <p data-testid="open-shifts-summary" class="mt-0.5 text-sm text-muted-foreground">
        <template v-if="openPlaces > 0">
          {{ t('dashboard.home.open.summaryPlaces', { count: openPlaces }, openPlaces) }}
          {{ t('dashboard.home.open.summaryShifts', { count: totalCount }, totalCount) }}
        </template>
        <template v-else>{{ t('dashboard.home.open.emptySummary') }}</template>
      </p>
    </div>

    <RouterLink
      data-testid="btn-browse-open-shifts"
      :to="OPEN_SHIFTS_ROUTE"
      class="order-last mt-0.5 flex min-h-12 items-center justify-center gap-1.5 rounded-xl border px-4 text-sm font-semibold text-foreground transition-colors hover:bg-accent/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none @4xl:order-none @4xl:col-start-2 @4xl:row-start-1 @4xl:mt-0 @4xl:min-h-9 @4xl:justify-end @4xl:border-0 @4xl:px-0 @4xl:text-primary @4xl:hover:bg-transparent @4xl:hover:underline"
    >
      {{ t('dashboard.home.open.browseAll') }}
      <span v-if="hiddenMobile > 0" data-testid="open-shifts-more-mobile" class="@4xl:hidden">
        {{ t('dashboard.home.open.moreCount', { count: hiddenMobile }) }}
      </span>
      <span
        v-if="hiddenDesktop > 0"
        data-testid="open-shifts-more-desktop"
        class="hidden @4xl:inline"
      >
        {{ t('dashboard.home.open.moreCount', { count: hiddenDesktop }) }}
      </span>
      <ArrowRight class="size-4 shrink-0" aria-hidden="true" />
    </RouterLink>

    <ul
      v-if="shifts.length"
      class="flex flex-col gap-2.5 @xl:grid @xl:grid-cols-2 @xl:gap-3 @4xl:col-span-2 @4xl:grid-cols-[repeat(auto-fill,minmax(18.75rem,1fr))] @4xl:gap-4"
    >
      <OpenShiftCard
        v-for="(shift, i) in shifts"
        :key="shift.shift_id"
        :shift="shift"
        :now="now"
        :show-event-name="showEventName"
        :class="i >= MOBILE_OPEN_SHIFT_LIMIT ? '@max-4xl:hidden' : ''"
        @select="emit('select', $event)"
      />
    </ul>
    <div
      v-else
      data-testid="open-shifts-empty"
      class="flex flex-col items-center gap-1 rounded-2xl border border-dashed px-4 py-8 text-center @4xl:col-span-2 @4xl:rounded-[18px]"
    >
      <p class="font-medium">{{ t('dashboard.home.open.emptyTitle') }}</p>
      <p class="text-sm text-muted-foreground">{{ t('dashboard.home.open.emptyBody') }}</p>
    </div>
  </section>
</template>
