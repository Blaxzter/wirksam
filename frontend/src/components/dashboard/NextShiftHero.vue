<script setup lang="ts">
/**
 * The one thing somebody opens this page to find out: where they are due next.
 *
 * It is the largest thing on the dashboard and the start time is the largest
 * thing in it, because that is the fact you are checking. The chip beside the
 * eyebrow answers the follow-up question, "how long have I got", from the
 * page's own clock, so it counts down while the page stays open and says
 * "happening now" once the shift has begun.
 *
 * On desktop a bar of the day sits underneath, with the shift drawn on it and
 * a marker for now. It repeats what the text says, so it is hidden from
 * screen readers, and it is left out for a shift without times.
 *
 * The buttons come right after the time in the DOM, because on desktop they
 * share its row (wrapping under it when the card is too narrow for both, as
 * with a 12-hour clock or the map button). On a phone they are moved to the
 * bottom of the card by `order`; they are the card's only focusable elements,
 * so the tab order is the same either way.
 *
 * With nothing booked the card turns into the offer instead: a page that says
 * "nothing booked" and stops there has wasted the best slot on the screen.
 * Both states carry `dashboard-next-shift`, so the tour's first step always
 * has something to point at.
 */
import { computed } from 'vue'

import {
  ArrowRight,
  CalendarCheck,
  CalendarDays,
  Map as MapIcon,
  MapPin,
  Search,
  Users,
} from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import { Button } from '@/components/ui/button'

import ShiftDayStrip from '@/components/dashboard/ShiftDayStrip.vue'

import type { DashboardShift } from '@/client'
import {
  OPEN_SHIFTS_ROUTE,
  capitalizeFirst,
  dayOffset,
  dayStrip,
  foreignEventName,
  mapLinkFor,
  shiftCountdown,
  shiftHeadline,
} from '@/lib/dashboard'

const props = defineProps<{
  shift: DashboardShift | null
  now: Date
  /** Places going begging in the event in view, for the empty state's offer. */
  openPlaces: number
  /** The selected event's id when it has a venue plan, else null. */
  venueMapEventId: string | null
  /** The event the feed is about, so a shift elsewhere is labelled. */
  currentEventId: string | null
  /**
   * The empty card has its row to itself on desktop (no voucher card beside
   * it). Only then are icon, words and button laid out in one line: at two
   * thirds of the width that line left a sentence floating in the middle of a
   * tall, empty card, so there it stays stacked, with the button at the
   * bottom as in the voucher card next to it.
   */
  alone?: boolean
}>()

const emit = defineEmits<{ open: [shift: DashboardShift] }>()

const { t, locale } = useI18n()
const { formatTimeRange, formatRelativeDay, formatDateLabel } = useFormatters()

const countdownText = computed(() => {
  const shift = props.shift
  if (!shift) return ''
  const c = shiftCountdown(shift, props.now)
  switch (c.kind) {
    case 'startsIn':
      if (c.hours === 0) return t('dashboard.home.next.countdown.minutes', { minutes: c.minutes })
      if (c.minutes === 0) return t('dashboard.home.next.countdown.hours', { hours: c.hours })
      return t('dashboard.home.next.countdown.hoursMinutes', { hours: c.hours, minutes: c.minutes })
    case 'running':
      return t('dashboard.home.next.countdown.running')
    case 'day':
      // No text-transform: the label arrives from `Intl.RelativeTimeFormat` as
      // a sentence ("in 6 days"), which reads well as a small chip.
      return formatRelativeDay(shift.date)
    default:
      // Over: the page reloads the feed and the next shift takes its place.
      return ''
  }
})

const times = computed(() =>
  props.shift ? formatTimeRange(props.shift.start_time, props.shift.end_time) : '',
)
const fullDate = computed(() =>
  props.shift
    ? formatDateLabel(props.shift.date, { weekday: 'long', day: 'numeric', month: 'long' })
    : '',
)
/**
 * The range in pieces that never break inside a time: "04:00 PM –" may wrap
 * onto a second line, "06:00 / PM" may not. A 12-hour range is half as long
 * again as "14:00 – 17:00", so it also steps the size down.
 */
const timePieces = computed(() => times.value.split(' – '))
const longTimes = computed(() => times.value.length > 13)
/** "Today", "Tomorrow", "Yesterday" for the days that have a word, else null. */
const relativeWord = computed(() => {
  if (!props.shift) return null
  const offset = dayOffset(props.shift.date, props.now)
  if (Math.abs(offset) > 1) return null
  return capitalizeFirst(formatRelativeDay(props.shift.date), locale.value)
})
const dateLine = computed(() => {
  if (!times.value) return relativeWord.value ?? ''
  return relativeWord.value
    ? t('dashboard.home.next.dateLine', { relative: relativeWord.value, date: fullDate.value })
    : fullDate.value
})

const heading = computed(() =>
  props.shift ? shiftHeadline(props.shift.title, props.shift.task_name) : null,
)
/** Everybody on the shift except you: "who else will be there". */
const others = computed(() => Math.max((props.shift?.taken ?? 1) - 1, 0))
const eventName = computed(() =>
  props.shift ? foreignEventName(props.shift, props.currentEventId) : null,
)
const mapTo = computed(() => mapLinkFor(props.shift, props.venueMapEventId))
const strip = computed(() => (props.shift ? dayStrip(props.shift, props.now) : null))
</script>

<template>
  <section
    v-if="shift"
    aria-labelledby="dashboard-next-title"
    data-testid="dashboard-next-shift"
    class="relative isolate overflow-hidden rounded-[20px] bg-primary p-5 text-primary-foreground @4xl:rounded-[22px] @4xl:px-8 @4xl:py-7"
  >
    <span
      aria-hidden="true"
      class="pointer-events-none absolute -top-14 -right-12 size-[170px] rounded-full bg-hero-speck opacity-[0.18] @4xl:-top-20 @4xl:-right-[60px] @4xl:size-[260px] @4xl:opacity-[0.16]"
    />
    <span
      aria-hidden="true"
      class="pointer-events-none absolute top-[70px] right-9 size-[52px] rounded-full bg-hero-speck opacity-[0.14] @4xl:top-10 @4xl:right-[150px] @4xl:size-16 @4xl:opacity-[0.12]"
    />

    <div class="relative flex flex-col gap-1">
      <div class="flex flex-wrap items-center gap-2 @4xl:gap-2.5">
        <h2
          id="dashboard-next-title"
          class="text-xs font-bold tracking-[0.06em] text-primary-foreground/85 uppercase"
        >
          {{ t('dashboard.home.next.eyebrow') }}
        </h2>
        <span
          v-if="countdownText"
          data-testid="next-shift-countdown"
          class="rounded-full bg-hero-chip px-2.5 py-0.5 text-[13px] font-bold text-hero-chip-foreground tabular-nums"
        >
          {{ countdownText }}
        </span>
      </div>

      <!--
        On a wide card the time and the buttons share a row, and the buttons
        drop under the time when both do not fit, rather than squeezing the
        time onto two lines. On a narrow card this wrapper dissolves
        (`contents`) and `order-last` sends the buttons to the end of the card.
      -->
      <div
        class="contents @4xl:mt-2.5 @4xl:flex @4xl:flex-wrap @4xl:items-end @4xl:justify-between @4xl:gap-x-6 @4xl:gap-y-4"
      >
        <div class="mt-3 min-w-0 @4xl:mt-0">
          <p
            v-if="times"
            data-testid="next-shift-times"
            class="leading-[1.05] font-bold tracking-[-0.02em] tabular-nums @4xl:leading-none @4xl:tracking-[-0.025em]"
            :class="longTimes ? 'text-[2rem] @4xl:text-5xl' : 'text-[2.5rem] @4xl:text-[3.5rem]'"
          >
            <template v-for="(piece, i) in timePieces" :key="i"
              ><span v-if="i > 0"> – </span
              ><span class="whitespace-nowrap">{{ piece }}</span></template
            >
          </p>
          <p v-else class="text-3xl leading-tight font-bold tracking-[-0.02em] @4xl:text-4xl">
            {{ fullDate }}
          </p>
          <p v-if="dateLine" class="text-sm text-primary-foreground/85 @4xl:mt-2 @4xl:text-[15px]">
            {{ dateLine }}
          </p>
        </div>

        <div class="order-last mt-[18px] flex gap-2 @4xl:order-none @4xl:mt-0 @4xl:flex-wrap">
          <Button
            data-testid="btn-open-next-shift"
            class="h-12 flex-1 rounded-xl bg-primary-foreground font-bold text-primary hover:bg-primary-foreground/90 focus-visible:ring-primary-foreground/60 @4xl:h-[46px] @4xl:flex-none @4xl:px-[18px] @4xl:has-[>svg]:px-[18px]"
            @click="emit('open', shift)"
          >
            {{ t('dashboard.home.next.open') }}
            <ArrowRight aria-hidden="true" />
          </Button>
          <Button
            v-if="mapTo"
            as-child
            variant="outline"
            class="size-12 shrink-0 rounded-xl border-primary-foreground/40 bg-transparent p-0 text-primary-foreground hover:bg-primary-foreground/10 hover:text-primary-foreground focus-visible:ring-primary-foreground/60 @4xl:-order-1 @4xl:h-[46px] @4xl:w-auto @4xl:px-[18px] @4xl:has-[>svg]:px-[18px] dark:border-primary-foreground/40 dark:bg-transparent dark:hover:bg-primary-foreground/10"
          >
            <RouterLink data-testid="btn-next-shift-map" :to="mapTo">
              <MapIcon class="size-5" aria-hidden="true" />
              <span class="sr-only @4xl:not-sr-only">{{ t('dashboard.home.next.onMap') }}</span>
            </RouterLink>
          </Button>
        </div>
      </div>

      <p
        class="mt-3.5 min-w-0 text-xl leading-tight font-semibold break-words @4xl:mt-[18px] @4xl:text-[22px]"
      >
        {{ heading?.headline }}
      </p>

      <div
        class="mt-0.5 flex min-w-0 flex-col gap-1 text-sm text-primary-foreground/85 @4xl:flex-row @4xl:flex-wrap @4xl:gap-x-[18px] @4xl:gap-y-1.5"
      >
        <span v-if="heading?.taskLine" class="truncate">{{ heading.taskLine }}</span>
        <span v-if="shift.location" class="flex min-w-0 items-center gap-1.5">
          <MapPin class="size-4 shrink-0" aria-hidden="true" />
          <span class="truncate">{{ shift.location }}</span>
        </span>
        <span class="flex items-center gap-1.5">
          <Users class="size-4 shrink-0" aria-hidden="true" />
          {{ t('dashboard.home.next.withOthers', { count: others }, others) }}
        </span>
        <span v-if="eventName" class="flex min-w-0 items-center gap-1.5">
          <CalendarDays class="size-4 shrink-0" aria-hidden="true" />
          <span class="truncate">{{ eventName }}</span>
        </span>
      </div>

      <ShiftDayStrip v-if="strip" :strip="strip" class="hidden @4xl:block" />
    </div>
  </section>

  <section
    v-else
    aria-labelledby="dashboard-next-empty-title"
    data-testid="dashboard-next-shift"
    class="flex flex-col gap-2.5 rounded-[20px] border bg-card p-5 text-card-foreground @4xl:rounded-[22px] @4xl:px-8 @4xl:py-7"
    :class="{
      '@4xl:flex-row @4xl:flex-wrap @4xl:items-center @4xl:gap-x-7 @4xl:gap-y-5': alone,
    }"
  >
    <span
      aria-hidden="true"
      class="flex size-12 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary @4xl:size-14"
    >
      <CalendarCheck class="size-6" />
    </span>
    <div :class="{ '@4xl:min-w-0 @4xl:flex-1 @4xl:basis-80': alone }">
      <h2
        id="dashboard-next-empty-title"
        class="mt-1 text-xl font-bold @4xl:text-[22px]"
        :class="{ '@4xl:mt-0': alone }"
      >
        {{ t('dashboard.home.next.empty.title') }}
      </h2>
      <p class="text-[15px] text-muted-foreground @4xl:mt-1">
        {{
          openPlaces > 0
            ? t('dashboard.home.next.empty.bodyOpen', { count: openPlaces }, openPlaces)
            : t('dashboard.home.next.empty.bodyNone')
        }}
      </p>
    </div>
    <div v-if="openPlaces > 0" class="mt-auto pt-2" :class="{ '@4xl:mt-0 @4xl:pt-0': alone }">
      <Button
        as-child
        class="h-12 w-full rounded-xl font-bold @4xl:px-5 @4xl:has-[>svg]:px-5"
        :class="{ '@4xl:w-auto': alone }"
      >
        <RouterLink data-testid="btn-find-shift" :to="OPEN_SHIFTS_ROUTE">
          <Search aria-hidden="true" />
          {{ t('dashboard.home.findShift') }}
        </RouterLink>
      </Button>
    </div>
  </section>
</template>
