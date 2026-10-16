<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { MapPin, ShieldCheck, Tag, Trash2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'

import HintTooltip from '@/components/utils/HintTooltip.vue'

import type { FeedShiftEntry, FeedTaskItem, ShiftWindowResponse } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { statusVariant } from '@/lib/status'

import WeekDayColumns from './WeekDayColumns.vue'
import type { DayColumn, DayShiftEntry } from './WeekDayColumns.vue'

const props = defineProps<{
  task: FeedTaskItem
  visibleDays?: number
  hideFullShifts?: boolean
}>()

const emit = defineEmits<{
  navigate: [task: FeedTaskItem]
  delete: [task: FeedTaskItem]
  clickShift: [slotId: string, task: FeedTaskItem]
}>()

const { t } = useI18n()
const authStore = useAuthStore()
const { get } = useAuthenticatedClient()

const canManage = computed(() => authStore.canManageEvent(props.task.event_id))

const numDays = computed(() => props.visibleDays ?? 5)
const expanded = ref(false)

/** Days fetched per request once the strip is swiped near either end. */
const CHUNK_DAYS = 10

function parseDate(value: string): Date {
  const [y, m, d] = value.split('-').map(Number)
  return new Date(y, m - 1, d)
}

function addDays(date: Date, days: number): Date {
  const d = new Date(date)
  d.setDate(d.getDate() + days)
  return d
}

function dateStr(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// Window start date from feed (initial window)
const initialWindowStart = computed(() => {
  if (props.task.slot_window_start) return parseDate(props.task.slot_window_start)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return today
})

/*
 * The strip holds one contiguous run of days, [rangeStart, rangeEnd), and
 * grows at either end as the user swipes there. It never grows past the
 * task's own dates — no shift can lie outside them — but always spans at
 * least the first window, so a task whose dates have passed still shows one.
 */
const rangeStart = ref(initialWindowStart.value)
const rangeEnd = ref(addDays(initialWindowStart.value, numDays.value))
const shiftsByDay = ref<Map<string, FeedShiftEntry[]>>(new Map())
const loadingNext = ref(false)
const loadingPrevious = ref(false)

const firstDay = computed(() => {
  const taskStart = parseDate(props.task.start_date)
  return taskStart < initialWindowStart.value ? taskStart : initialWindowStart.value
})
const lastDay = computed(() => parseDate(props.task.end_date))

const hasMoreNext = computed(() => rangeEnd.value <= lastDay.value)
const hasMorePrevious = computed(() => rangeStart.value > firstDay.value)

function groupByDay(shifts: FeedShiftEntry[]): Map<string, FeedShiftEntry[]> {
  const map = new Map<string, FeedShiftEntry[]>()
  for (const shift of shifts) {
    if (!map.has(shift.date)) map.set(shift.date, [])
    map.get(shift.date)!.push(shift)
  }
  return map
}

function resetStrip() {
  rangeStart.value = initialWindowStart.value
  rangeEnd.value = addDays(initialWindowStart.value, numDays.value)
  shiftsByDay.value = groupByDay(props.task.shifts ?? [])
}
resetStrip()

function toDayEntry(shift: FeedShiftEntry): DayShiftEntry {
  return {
    slotId: shift.id,
    startTime: shift.start_time,
    endTime: shift.end_time,
    currentBookings: shift.current_bookings,
    maxBookings: shift.max_bookings,
    isBookedByMe: shift.is_booked_by_me,
    collidesWithMyBooking: shift.collides_with_my_booking,
  }
}

const days = computed<DayColumn[]>(() => {
  const result: DayColumn[] = []
  for (let date = rangeStart.value; date < rangeEnd.value; date = addDays(date, 1)) {
    const ds = dateStr(date)
    const dayShifts = (shiftsByDay.value.get(ds) ?? []).map(toDayEntry)
    dayShifts.sort((a, b) => (a.startTime ?? '').localeCompare(b.startTime ?? ''))
    result.push({ date, dateStr: ds, shifts: dayShifts })
  }
  return result
})

const totalAvailableShifts = computed(() => {
  const shifts = props.task.shifts ?? []
  return shifts.filter((s) => {
    if (!s.max_bookings) return true
    return (s.current_bookings ?? 0) < s.max_bookings
  }).length
})

async function fetchDays(start: Date, count: number): Promise<boolean> {
  try {
    const res = await get<{ data: ShiftWindowResponse }>({
      url: `/tasks/${props.task.id}/shift-window`,
      query: { start_date: dateStr(start), days: count },
    })
    const fetched = groupByDay(res.data.shifts)
    const merged = new Map(shiftsByDay.value)
    for (let i = 0; i < count; i++) {
      const day = dateStr(addDays(start, i))
      merged.set(day, fetched.get(day) ?? [])
    }
    shiftsByDay.value = merged
    return true
  } catch (error) {
    toastApiError(error)
    return false
  }
}

async function loadNext() {
  if (loadingNext.value || !hasMoreNext.value) return
  loadingNext.value = true
  const start = rangeEnd.value
  const remaining = Math.round((lastDay.value.getTime() - start.getTime()) / 86_400_000) + 1
  const count = Math.min(CHUNK_DAYS, remaining)
  if (await fetchDays(start, count)) rangeEnd.value = addDays(start, count)
  loadingNext.value = false
}

async function loadPrevious() {
  if (loadingPrevious.value || !hasMorePrevious.value) return
  loadingPrevious.value = true
  const earliest = addDays(rangeStart.value, -CHUNK_DAYS)
  const start = earliest < firstDay.value ? firstDay.value : earliest
  const count = Math.round((rangeStart.value.getTime() - start.getTime()) / 86_400_000)
  if (await fetchDays(start, count)) rangeStart.value = start
  loadingPrevious.value = false
}

// A different task, or a different starting day, starts the strip over.
watch(
  () => [props.task.id, props.task.slot_window_start],
  () => resetStrip(),
)

// The feed re-fetched (after a booking, say): take its shifts and re-read the
// days loaded beyond them, so the strip stays where the user swiped it.
watch(
  () => props.task.shifts,
  async (shifts) => {
    const fromFeed = groupByDay(shifts ?? [])
    const merged = new Map(shiftsByDay.value)
    for (let i = 0; i < numDays.value; i++) {
      const day = dateStr(addDays(initialWindowStart.value, i))
      merged.set(day, fromFeed.get(day) ?? [])
    }
    shiftsByDay.value = merged
    const windowEnd = addDays(initialWindowStart.value, numDays.value)
    for (let start = rangeStart.value; start < rangeEnd.value; start = addDays(start, 31)) {
      const end = addDays(start, 31) < rangeEnd.value ? addDays(start, 31) : rangeEnd.value
      // The feed's own window is fresh already.
      if (start >= initialWindowStart.value && end <= windowEnd) continue
      const count = Math.round((end.getTime() - start.getTime()) / 86_400_000)
      await fetchDays(start, count)
    }
  },
)
</script>

<template>
  <div
    data-testid="task-row"
    class="overflow-hidden rounded-lg border bg-card transition-colors hover:bg-muted/30"
  >
    <div class="flex flex-col md:flex-row md:min-h-[260px]">
      <!-- Top/Left: Task Info -->
      <div
        data-testid="task-row-info"
        class="flex cursor-pointer flex-col justify-between border-b p-4 md:w-56 md:shrink-0 md:border-b-0 md:border-r"
        @click="emit('navigate', task)"
      >
        <div class="space-y-2">
          <div class="flex items-start justify-between gap-2">
            <h3 class="text-sm font-semibold leading-tight line-clamp-2 break-words">
              {{ task.name }}
            </h3>
            <div v-if="canManage" class="flex shrink-0 items-center gap-1">
              <ShieldCheck class="h-3.5 w-3.5 text-primary" />
              <Badge :variant="statusVariant(task.status)" class="text-[10px]">
                {{ t(`duties.tasks.statuses.${task.status ?? 'draft'}`) }}
              </Badge>
            </div>
          </div>

          <p v-if="task.description" class="text-xs text-muted-foreground line-clamp-2 break-words">
            {{ task.description }}
          </p>

          <div class="space-y-1">
            <div v-if="task.location" class="flex items-center gap-1 text-xs text-muted-foreground">
              <MapPin class="h-3 w-3 shrink-0" />
              <span class="truncate">{{ task.location }}</span>
            </div>
            <div v-if="task.category" class="flex items-center gap-1 text-xs text-muted-foreground">
              <Tag class="h-3 w-3 shrink-0" />
              <span class="truncate">{{ task.category }}</span>
            </div>
          </div>
        </div>

        <div class="mt-3 flex items-center justify-between">
          <span class="text-xs text-muted-foreground">
            {{ t('duties.tasks.quickView.availableShifts', { count: totalAvailableShifts }) }}
          </span>
          <HintTooltip v-if="canManage" :label="t('duties.tasks.delete')">
            <Button
              variant="ghost"
              size="icon"
              class="h-6 w-6"
              :aria-label="t('duties.tasks.delete')"
              @click.stop="emit('delete', task)"
            >
              <Trash2 class="h-3.5 w-3.5 text-destructive" />
            </Button>
          </HintTooltip>
        </div>
      </div>

      <!-- Right: Week Day Columns -->
      <div data-testid="task-row-days" class="flex min-h-0 flex-1 flex-col p-2">
        <WeekDayColumns
          ref="weekColumns"
          :days="days"
          :visible-days="numDays"
          :expanded="expanded"
          :hide-full-shifts="hideFullShifts"
          :has-more-next="hasMoreNext"
          :has-more-previous="hasMorePrevious"
          :loading-next="loadingNext"
          :loading-previous="loadingPrevious"
          @load-next="loadNext"
          @load-previous="loadPrevious"
          @click-shift="(slotId) => emit('clickShift', slotId, task)"
          @toggle-expand="expanded = !expanded"
        />
      </div>
    </div>
  </div>
</template>
