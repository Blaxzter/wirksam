<script setup lang="ts">
import { computed, ref } from 'vue'

import { CalendarDays, ChevronLeft, ChevronRight, Clock, List } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

import type { EventGroupRead, EventRead } from '@/client/types.gen'
import Button from '@/components/ui/button/Button.vue'

import DutyCalendarDay from './DutyCalendarDay.vue'
import DutyCalendarMonth from './DutyCalendarMonth.vue'
import DutyCalendarWeek from './DutyCalendarWeek.vue'
import type { BookingCalendarItem, CalendarDay as CalendarDayType, CalendarWeek, ViewMode } from './types'
import { computeEventBars, computeGroupBars, dateToStr, EMPTY_DAY } from './types'

const props = withDefaults(
  defineProps<{
    events?: EventRead[]
    eventGroups?: EventGroupRead[]
    bookings?: BookingCalendarItem[]
    showEvents?: boolean
    showGroups?: boolean
    showBookings?: boolean
    defaultView?: ViewMode
  }>(),
  {
    events: () => [],
    eventGroups: () => [],
    bookings: () => [],
    showEvents: true,
    showGroups: true,
    showBookings: true,
    defaultView: 'month',
  },
)

const emit = defineEmits<{
  navigateEvent: [event: EventRead]
  navigateGroup: [group: EventGroupRead]
  navigateBooking: [booking: BookingCalendarItem]
}>()

const { t, locale } = useI18n()

const viewMode = ref<ViewMode>(props.defaultView)
const calendarDate = ref(new Date())
const hoveredGroupId = ref<string | null>(null)
const hoveredEventId = ref<string | null>(null)

// ── Helpers ──

const weekdayNames = computed(() => {
  const fmt = new Intl.DateTimeFormat(locale.value, { weekday: 'short' })
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, i + 1)))
})

function buildDay(date: Date): CalendarDayType {
  const dateStr = dateToStr(date)
  return {
    date,
    dateStr,
    events: props.showEvents
      ? props.events.filter((e) => e.start_date <= dateStr && e.end_date >= dateStr)
      : [],
    groups: props.showGroups
      ? props.eventGroups.filter((g) => g.start_date <= dateStr && g.end_date >= dateStr)
      : [],
    bookings: props.showBookings
      ? props.bookings.filter((b) => b.date === dateStr)
      : [],
  }
}

function getWeekStart(d: Date): Date {
  const copy = new Date(d)
  const dow = copy.getDay()
  const diff = dow === 0 ? 6 : dow - 1
  copy.setDate(copy.getDate() - diff)
  return new Date(copy.getFullYear(), copy.getMonth(), copy.getDate())
}

// ── Month view data ──

const calendarWeeks = computed<CalendarWeek[]>(() => {
  const year = calendarDate.value.getFullYear()
  const month = calendarDate.value.getMonth()
  const lastDay = new Date(year, month + 1, 0)

  const firstDow = new Date(year, month, 1).getDay()
  const startDow = firstDow === 0 ? 6 : firstDow - 1

  const allDays: CalendarDayType[] = []
  for (let i = 0; i < startDow; i++) allDays.push(EMPTY_DAY)
  for (let d = 1; d <= lastDay.getDate(); d++) allDays.push(buildDay(new Date(year, month, d)))
  while (allDays.length % 7 !== 0) allDays.push(EMPTY_DAY)

  const weeks: CalendarWeek[] = []
  for (let i = 0; i < allDays.length; i += 7) {
    const days = allDays.slice(i, i + 7)
    const groupBars = computeGroupBars(days)
    const eventBars = computeEventBars(days)
    weeks.push({ days, groupBars, eventBars, barLaneCount: groupBars.length, eventBarLaneCount: eventBars.length })
  }
  return weeks
})

// ── Week view data ──

const currentWeek = computed<CalendarWeek>(() => {
  const start = getWeekStart(calendarDate.value)
  const days: CalendarDayType[] = []
  for (let i = 0; i < 7; i++) {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    days.push(buildDay(d))
  }
  const groupBars = computeGroupBars(days)
  const eventBars = computeEventBars(days)
  return { days, groupBars, eventBars, barLaneCount: groupBars.length, eventBarLaneCount: eventBars.length }
})

// ── Day view data ──

const currentDay = computed<CalendarDayType>(() => buildDay(calendarDate.value))

// ── Navigation ──

const headerTitle = computed(() => {
  const d = calendarDate.value
  if (viewMode.value === 'month') {
    return d.toLocaleDateString(locale.value, { month: 'long', year: 'numeric' })
  }
  if (viewMode.value === 'week') {
    const start = getWeekStart(d)
    const end = new Date(start)
    end.setDate(start.getDate() + 6)
    const opts: Intl.DateTimeFormatOptions =
      start.getMonth() === end.getMonth()
        ? { day: 'numeric' }
        : { month: 'short', day: 'numeric' }
    const startStr = start.toLocaleDateString(locale.value, { month: 'short', day: 'numeric' })
    const endStr = end.toLocaleDateString(locale.value, { ...opts, year: 'numeric' })
    return `${startStr} – ${endStr}`
  }
  return d.toLocaleDateString(locale.value, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })
})

const navigatePrev = () => {
  const d = new Date(calendarDate.value)
  if (viewMode.value === 'month') d.setMonth(d.getMonth() - 1)
  else if (viewMode.value === 'week') d.setDate(d.getDate() - 7)
  else d.setDate(d.getDate() - 1)
  calendarDate.value = d
}

const navigateNext = () => {
  const d = new Date(calendarDate.value)
  if (viewMode.value === 'month') d.setMonth(d.getMonth() + 1)
  else if (viewMode.value === 'week') d.setDate(d.getDate() + 7)
  else d.setDate(d.getDate() + 1)
  calendarDate.value = d
}

const goToToday = () => {
  calendarDate.value = new Date()
}

const goToDay = (day: CalendarDayType) => {
  if (!day.date) return
  calendarDate.value = new Date(day.date)
  viewMode.value = 'day'
}
</script>

<template>
  <!-- Header: view mode + navigation -->
  <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
    <!-- View mode switcher -->
    <div class="flex overflow-hidden rounded-md border">
      <Button
        :variant="viewMode === 'month' ? 'default' : 'ghost'"
        size="sm"
        class="rounded-none border-0"
        @click="viewMode = 'month'"
      >
        <CalendarDays class="mr-1.5 h-4 w-4" />
        <span class="hidden sm:inline">{{ t('duties.events.calendar.views.month') }}</span>
      </Button>
      <Button
        :variant="viewMode === 'week' ? 'default' : 'ghost'"
        size="sm"
        class="rounded-none border-0 border-l"
        @click="viewMode = 'week'"
      >
        <List class="mr-1.5 h-4 w-4" />
        <span class="hidden sm:inline">{{ t('duties.events.calendar.views.week') }}</span>
      </Button>
      <Button
        :variant="viewMode === 'day' ? 'default' : 'ghost'"
        size="sm"
        class="rounded-none border-0 border-l"
        @click="viewMode = 'day'"
      >
        <Clock class="mr-1.5 h-4 w-4" />
        <span class="hidden sm:inline">{{ t('duties.events.calendar.views.day') }}</span>
      </Button>
    </div>

    <!-- Date navigation -->
    <div class="flex items-center gap-2">
      <Button variant="outline" size="sm" @click="goToToday">
        {{ t('duties.events.calendar.today') }}
      </Button>
      <Button variant="outline" size="icon" class="h-8 w-8" @click="navigatePrev">
        <ChevronLeft class="h-4 w-4" />
      </Button>
      <h2 class="min-w-[140px] text-center text-base font-semibold capitalize sm:text-lg">
        {{ headerTitle }}
      </h2>
      <Button variant="outline" size="icon" class="h-8 w-8" @click="navigateNext">
        <ChevronRight class="h-4 w-4" />
      </Button>
    </div>
  </div>

  <!-- View components -->
  <DutyCalendarMonth
    v-if="viewMode === 'month'"
    :weeks="calendarWeeks"
    :weekday-names="weekdayNames"
    :hovered-group-id="hoveredGroupId"
    :hovered-event-id="hoveredEventId"
    @navigate-event="emit('navigateEvent', $event)"
    @navigate-group="emit('navigateGroup', $event)"
    @navigate-booking="emit('navigateBooking', $event)"
    @hover-group="hoveredGroupId = $event"
    @hover-event="hoveredEventId = $event"
    @select-day="goToDay"
  />

  <DutyCalendarWeek
    v-else-if="viewMode === 'week'"
    :week="currentWeek"
    :weekday-names="weekdayNames"
    :hovered-group-id="hoveredGroupId"
    :hovered-event-id="hoveredEventId"
    @navigate-event="emit('navigateEvent', $event)"
    @navigate-group="emit('navigateGroup', $event)"
    @navigate-booking="emit('navigateBooking', $event)"
    @hover-group="hoveredGroupId = $event"
    @hover-event="hoveredEventId = $event"
    @select-day="goToDay"
  />

  <DutyCalendarDay
    v-else
    :day="currentDay"
    @navigate-event="emit('navigateEvent', $event)"
    @navigate-group="emit('navigateGroup', $event)"
    @navigate-booking="emit('navigateBooking', $event)"
  />
</template>
