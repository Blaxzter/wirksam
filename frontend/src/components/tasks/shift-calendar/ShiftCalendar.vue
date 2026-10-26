<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import { CalendarDays, ChevronDown, ChevronLeft, ChevronRight, Clock, List } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import Button from '@/components/ui/button/Button.vue'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

import ShiftCalendarDay from './ShiftCalendarDay.vue'
import ShiftCalendarMonth from './ShiftCalendarMonth.vue'
import ShiftCalendarWeek from './ShiftCalendarWeek.vue'
import type {
  BookingCalendarItem,
  CalendarDay as CalendarDayType,
  CalendarEvent,
  CalendarTask,
  CalendarWeek,
  DateRange,
  ViewMode,
} from './types'
import { EMPTY_DAY, computeEventBars, computeTaskBars, dateToStr } from './types'

const props = withDefaults(
  defineProps<{
    tasks?: CalendarTask[]
    events?: CalendarEvent[]
    bookings?: BookingCalendarItem[]
    showTasks?: boolean
    showGroups?: boolean
    showBookings?: boolean
    defaultView?: ViewMode
    calendarViewMode?: ViewMode
    calendarDate?: string // YYYY-MM-DD, controls the focused date
  }>(),
  {
    tasks: () => [],
    events: () => [],
    bookings: () => [],
    showTasks: true,
    showGroups: true,
    showBookings: true,
    defaultView: 'month',
    calendarViewMode: undefined,
    calendarDate: undefined,
  },
)

const emit = defineEmits<{
  navigateTask: [task: CalendarTask]
  navigateGroup: [event: CalendarEvent]
  navigateBooking: [booking: BookingCalendarItem]
  'update:dateRange': [range: DateRange]
  'update:calendarViewMode': [mode: ViewMode]
  'update:calendarDate': [date: string]
}>()

const { t, locale } = useI18n()

const viewMode = ref<ViewMode>(props.calendarViewMode ?? props.defaultView)
const calendarDate = ref(
  props.calendarDate ? new Date(props.calendarDate + 'T00:00:00') : new Date(),
)
const hoveredEventId = ref<string | null>(null)
const hoveredTaskId = ref<string | null>(null)

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
    tasks: props.showTasks
      ? props.tasks.filter((e) => e.start_date <= dateStr && e.end_date >= dateStr)
      : [],
    events: props.showGroups
      ? props.events.filter((g) => g.start_date <= dateStr && g.end_date >= dateStr)
      : [],
    bookings: props.showBookings ? props.bookings.filter((b) => b.date === dateStr) : [],
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
    const groupBars = computeEventBars(days)
    const eventBars = computeTaskBars(days)
    weeks.push({
      days,
      groupBars,
      eventBars,
      barLaneCount: groupBars.length,
      eventBarLaneCount: eventBars.length,
    })
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
  const groupBars = computeEventBars(days)
  const eventBars = computeTaskBars(days)
  return {
    days,
    groupBars,
    eventBars,
    barLaneCount: groupBars.length,
    eventBarLaneCount: eventBars.length,
  }
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
      start.getMonth() === end.getMonth() ? { day: 'numeric' } : { month: 'short', day: 'numeric' }
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

// ── Month picker ──

const pickerOpen = ref(false)
const monthPickerScroll = ref<HTMLElement>()
const activeMonthBtn = ref<HTMLElement | null>(null)

const monthNamesShort = computed(() => {
  const fmt = new Intl.DateTimeFormat(locale.value, { month: 'short' })
  return Array.from({ length: 12 }, (_, i) => fmt.format(new Date(2024, i, 1)))
})

type MonthPickerEntry =
  | { kind: 'year'; key: string; year: number }
  | {
      kind: 'month'
      key: string
      year: number
      month: number
      label: string
      isActive: boolean
    }

const monthPickerItems = computed<MonthPickerEntry[]>(() => {
  const activeYear = calendarDate.value.getFullYear()
  const activeMonth = calendarDate.value.getMonth()
  const startYear = activeYear - 3
  const endYear = activeYear + 3
  const entries: MonthPickerEntry[] = []
  for (let y = startYear; y <= endYear; y++) {
    entries.push({ kind: 'year', key: `y-${y}`, year: y })
    for (let m = 0; m < 12; m++) {
      entries.push({
        kind: 'month',
        key: `m-${y}-${m}`,
        year: y,
        month: m,
        label: monthNamesShort.value[m] ?? '',
        isActive: y === activeYear && m === activeMonth,
      })
    }
  }
  return entries
})

const selectMonth = (year: number, month: number) => {
  const d = new Date(calendarDate.value)
  d.setFullYear(year)
  d.setMonth(month)
  calendarDate.value = d
  pickerOpen.value = false
}

watch(pickerOpen, async (open) => {
  if (!open) return
  await nextTick()
  activeMonthBtn.value?.scrollIntoView({ behavior: 'auto', block: 'nearest', inline: 'center' })
})

const goToDay = (day: CalendarDayType) => {
  if (!day.date) return
  calendarDate.value = new Date(day.date)
  viewMode.value = 'day'
}

// ── Visible date range (emitted for parent to fetch data) ──

const visibleRange = computed<DateRange>(() => {
  const d = calendarDate.value
  if (viewMode.value === 'month') {
    const year = d.getFullYear()
    const month = d.getMonth()
    return {
      from: dateToStr(new Date(year, month, 1)),
      to: dateToStr(new Date(year, month + 1, 0)),
    }
  }
  if (viewMode.value === 'week') {
    const start = getWeekStart(d)
    const end = new Date(start)
    end.setDate(start.getDate() + 6)
    return { from: dateToStr(start), to: dateToStr(end) }
  }
  // day
  const ds = dateToStr(d)
  return { from: ds, to: ds }
})

watch(visibleRange, (range) => emit('update:dateRange', range), { immediate: true })

// Emit internal state changes so parent can mirror to URL
watch(viewMode, (mode) => emit('update:calendarViewMode', mode))
watch(calendarDate, (d) => emit('update:calendarDate', dateToStr(d)))
</script>

<template>
  <!-- Header: view mode + navigation -->
  <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
    <!-- View mode switcher -->
    <Tabs v-model="viewMode" class="w-full sm:w-auto">
      <TabsList class="grid w-full grid-cols-3 sm:w-auto sm:inline-flex">
        <TabsTrigger value="month">
          <CalendarDays class="h-4 w-4" />
          {{ t('duties.tasks.calendar.views.month') }}
        </TabsTrigger>
        <TabsTrigger value="week">
          <List class="h-4 w-4" />
          {{ t('duties.tasks.calendar.views.week') }}
        </TabsTrigger>
        <TabsTrigger value="day">
          <Clock class="h-4 w-4" />
          {{ t('duties.tasks.calendar.views.day') }}
        </TabsTrigger>
      </TabsList>
    </Tabs>

    <!-- Date navigation -->
    <div class="flex items-center gap-2">
      <Button variant="outline" size="sm" @click="goToToday">
        {{ t('duties.tasks.calendar.today') }}
      </Button>
      <Button
        variant="outline"
        size="icon"
        class="hidden h-8 w-8 sm:inline-flex"
        :aria-label="t('duties.tasks.calendar.previous')"
        @click="navigatePrev"
      >
        <ChevronLeft class="h-4 w-4" />
      </Button>
      <Button
        variant="outline"
        size="sm"
        class="min-w-[160px] flex-1 justify-between gap-2 capitalize sm:flex-none"
        :aria-expanded="pickerOpen"
        @click="pickerOpen = !pickerOpen"
      >
        <span>{{ headerTitle }}</span>
        <ChevronDown
          class="h-4 w-4 shrink-0 transition-transform duration-200"
          :class="pickerOpen ? 'rotate-180' : ''"
        />
      </Button>
      <Button
        variant="outline"
        size="icon"
        class="hidden h-8 w-8 sm:inline-flex"
        :aria-label="t('duties.tasks.calendar.next')"
        @click="navigateNext"
      >
        <ChevronRight class="h-4 w-4" />
      </Button>
    </div>
  </div>

  <!-- Inline month picker -->
  <div
    v-if="pickerOpen"
    ref="monthPickerScroll"
    class="flex items-center gap-2 overflow-x-auto no-scrollbar touch-pan-x rounded-md border bg-muted/30 p-2"
  >
    <template v-for="entry in monthPickerItems" :key="entry.key">
      <div
        v-if="entry.kind === 'year'"
        class="shrink-0 px-1 text-xs font-semibold text-muted-foreground"
      >
        {{ entry.year }}
      </div>
      <button
        v-else
        :ref="
          (el) => {
            if (entry.isActive) activeMonthBtn = el as HTMLElement
          }
        "
        type="button"
        class="shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium transition-all"
        :class="
          entry.isActive
            ? 'bg-primary text-primary-foreground shadow-sm'
            : 'bg-background text-muted-foreground hover:bg-background/80'
        "
        @click="selectMonth(entry.year, entry.month)"
      >
        {{ entry.label }}
      </button>
    </template>
  </div>

  <!-- View components -->
  <ShiftCalendarMonth
    v-if="viewMode === 'month'"
    :weeks="calendarWeeks"
    :weekday-names="weekdayNames"
    :hovered-event-id="hoveredEventId"
    :hovered-task-id="hoveredTaskId"
    @navigate-task="emit('navigateTask', $event)"
    @navigate-event="emit('navigateGroup', $event)"
    @navigate-booking="emit('navigateBooking', $event)"
    @hover-event="hoveredEventId = $event"
    @hover-task="hoveredTaskId = $event"
    @select-day="goToDay"
  />

  <ShiftCalendarWeek
    v-else-if="viewMode === 'week'"
    :week="currentWeek"
    :weekday-names="weekdayNames"
    :hovered-event-id="hoveredEventId"
    :hovered-task-id="hoveredTaskId"
    @navigate-task="emit('navigateTask', $event)"
    @navigate-event="emit('navigateGroup', $event)"
    @navigate-booking="emit('navigateBooking', $event)"
    @hover-event="hoveredEventId = $event"
    @hover-task="hoveredTaskId = $event"
    @select-day="goToDay"
  />

  <ShiftCalendarDay
    v-else
    :day="currentDay"
    @navigate-task="emit('navigateTask', $event)"
    @navigate-event="emit('navigateGroup', $event)"
    @navigate-booking="emit('navigateBooking', $event)"
  />
</template>

<style scoped>
.no-scrollbar {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
.no-scrollbar::-webkit-scrollbar {
  display: none;
}
</style>
