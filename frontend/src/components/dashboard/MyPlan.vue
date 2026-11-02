<script setup lang="ts">
/**
 * "Your plan": every upcoming shift you have said yes to, day by day.
 *
 * It replaced a list headed "After that", which left out the next shift
 * because the card above already showed it. That made a second list that
 * started in the middle, and one booking meant no list at all. Now the plan is
 * complete, the next shift is simply marked "Up next", and a rail down the
 * side keeps the times in one column so a day reads top to bottom.
 *
 * Your duties are listed across every event you belong to; one in another
 * event than the one in view carries that event's name, so two schedules do
 * not silently mix. The feed sends at most six rows; the line under the list
 * says how many more there are and the link beside the heading opens them all.
 */
import { computed } from 'vue'

import { ArrowRight, ChevronRight } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import { Button } from '@/components/ui/button'

import type { DashboardShift } from '@/client'
import {
  capitalizeFirst,
  foreignEventName,
  groupByDay,
  hiddenCount,
  hoursValue,
  shiftHeadline,
} from '@/lib/dashboard'

const props = defineProps<{
  /** All of feed.my_shifts, soonest first. */
  shifts: DashboardShift[]
  /** feed.my_shift_count */
  totalCount: number
  /** feed.my_minutes */
  minutes: number
  /** feed.event_id */
  currentEventId: string | null
  now: Date
}>()

const emit = defineEmits<{ select: [shiftId: string] }>()

const { t, locale } = useI18n()
const { formatTime, formatTimeRange, formatRelativeDay, formatDateLabel } = useFormatters()

const nextId = computed(() => props.shifts[0]?.booking_id ?? null)
const hidden = computed(() => hiddenCount(props.totalCount, props.shifts.length))

const days = computed(() =>
  groupByDay(props.shifts, props.now).map((day) => {
    const date = formatDateLabel(day.date, { weekday: 'short', day: 'numeric', month: 'long' })
    // `formatRelativeDay` reads the clock itself; `groupByDay` read `now`, so
    // this still re-runs when the page's clock ticks past midnight.
    const heading =
      Math.abs(day.offset) <= 1
        ? t('dashboard.home.plan.dayHeading', {
            relative: capitalizeFirst(formatRelativeDay(day.date), locale.value),
            date,
          })
        : date
    return {
      date: day.date,
      heading,
      rows: day.items.map((shift) => {
        const { headline, taskLine } = shiftHeadline(shift.title, shift.task_name)
        return {
          shift,
          headline,
          detail: [taskLine, shift.location].filter(Boolean).join(' · '),
          eventName: foreignEventName(shift, props.currentEventId),
          isNext: shift.booking_id === nextId.value,
        }
      }),
    }
  }),
)
</script>

<template>
  <section
    id="dashboard-plan"
    data-testid="dashboard-my-shifts"
    aria-labelledby="dashboard-plan-title"
    class="min-w-0 scroll-mt-[calc(var(--demo-banner-height,0px)+1rem)] lg:rounded-[22px] lg:border lg:bg-card lg:px-4 lg:pt-5 lg:pb-3 lg:text-card-foreground"
  >
    <div
      class="mb-1.5 flex items-center justify-between gap-2 lg:mb-0 lg:items-start lg:px-2 lg:pb-1"
    >
      <div class="min-w-0">
        <h2
          id="dashboard-plan-title"
          tabindex="-1"
          class="text-[17px] font-bold focus:outline-none lg:text-lg"
        >
          {{ t('dashboard.home.plan.title') }}
        </h2>
        <p data-testid="plan-summary" class="mt-0.5 hidden text-sm text-muted-foreground lg:block">
          {{ t('dashboard.home.committed.shifts', { count: totalCount }, totalCount)
          }}<template v-if="minutes > 0">
            ·
            {{ t('dashboard.home.plan.summaryHours', { hours: hoursValue(minutes, locale) }) }}
          </template>
        </p>
      </div>
      <Button
        as-child
        variant="link"
        class="h-11 shrink-0 px-0 font-semibold has-[>svg]:px-0 lg:h-9"
      >
        <RouterLink data-testid="btn-all-bookings" :to="{ name: 'my-bookings' }">
          {{ t('dashboard.home.plan.all') }}
          <ArrowRight aria-hidden="true" />
        </RouterLink>
      </Button>
    </div>

    <div
      class="rounded-2xl border bg-card pt-1 pb-1.5 text-card-foreground lg:rounded-none lg:border-0 lg:bg-transparent lg:p-0"
    >
      <template v-for="day in days" :key="day.date">
        <h3
          class="px-4 pt-3 pb-1 text-xs font-bold tracking-[0.05em] text-muted-foreground uppercase lg:px-2 lg:pt-3.5"
        >
          {{ day.heading }}
        </h3>
        <ul class="px-2 lg:px-0">
          <li v-for="row in day.rows" :key="row.shift.booking_id">
            <button
              type="button"
              data-testid="plan-row"
              :data-shift-id="row.shift.shift_id"
              class="flex w-full items-stretch gap-3 rounded-xl px-2 py-2.5 text-left transition-colors hover:bg-accent/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none lg:min-h-14 lg:items-center lg:gap-4 lg:py-2"
              @click="emit('select', row.shift.shift_id)"
            >
              <span
                aria-hidden="true"
                class="w-1 shrink-0 self-stretch rounded-full lg:order-2"
                :class="row.isNext ? 'bg-primary' : 'bg-primary/30'"
              />
              <span
                class="max-w-18 min-w-[50px] shrink-0 text-sm leading-snug tabular-nums lg:order-1 lg:w-28 lg:max-w-none lg:min-w-0 lg:text-[15px] lg:font-bold"
              >
                <span class="lg:hidden">
                  <span
                    class="block font-bold"
                    :class="{ 'whitespace-nowrap': row.shift.start_time }"
                  >
                    {{ formatTime(row.shift.start_time) || t('dashboard.home.plan.noTime') }}
                  </span>
                  {{ ' ' }}
                  <span
                    v-if="row.shift.end_time"
                    class="block whitespace-nowrap text-muted-foreground"
                  >
                    {{ formatTime(row.shift.end_time) }}
                  </span>
                </span>
                <span class="hidden lg:inline">
                  {{
                    formatTimeRange(row.shift.start_time, row.shift.end_time) ||
                    t('dashboard.home.plan.noTime')
                  }}
                </span>
              </span>
              {{ ' ' }}
              <span class="min-w-0 flex-1 lg:order-3">
                <span class="block truncate text-[15px] font-semibold">{{ row.headline }}</span>
                {{ ' ' }}
                <span v-if="row.detail" class="block truncate text-[13px] text-muted-foreground">
                  {{ row.detail }}
                </span>
                <span
                  v-if="row.eventName"
                  data-testid="plan-row-event"
                  class="block truncate text-xs text-muted-foreground"
                >
                  {{ row.eventName }}
                </span>
              </span>
              {{ ' ' }}
              <span
                v-if="row.isNext"
                data-testid="plan-next-badge"
                class="shrink-0 self-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-bold text-primary lg:order-4 lg:px-2.5"
              >
                {{ t('dashboard.home.plan.next') }}
              </span>
              <ChevronRight
                aria-hidden="true"
                class="hidden size-4 shrink-0 self-center text-muted-foreground lg:order-5 lg:block"
              />
            </button>
          </li>
        </ul>
      </template>
      <p
        v-if="hidden > 0"
        data-testid="plan-more"
        class="px-4 pt-1 pb-2 text-xs text-muted-foreground lg:px-2"
      >
        {{ t('dashboard.home.plan.more', { count: hidden }, hidden) }}
      </p>
    </div>
  </section>
</template>
