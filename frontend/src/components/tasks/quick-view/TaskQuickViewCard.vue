<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'

import {
  Lock,
  MapPin,
  ScanLine,
  ShieldCheck,
  Tag,
  Ticket,
  Trash2,
  UserCheck,
  UsersRound,
} from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useFormatters } from '@/composables/useFormatters'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'

import TeamJoinButton from '@/components/tasks/TeamJoinButton.vue'
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
  teamJoined: []
}>()

const { t } = useI18n()
const authStore = useAuthStore()
const { get } = useAuthenticatedClient()
const { formatDateLabel } = useFormatters()

/** Organisers and the task's people in charge see its status. */
const canManage = computed(() => props.task.can_manage ?? false)
/** Deleting the task stays with the organisers. */
const canAdminEvent = computed(() => authStore.canManageEvent(props.task.event_id))

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
    lockedByTeam: shift.locked_by_team,
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

/**
 * What there is to book, over every shift still to come rather than the days
 * on screen: a task whose only shift is ten days out is listed, and saying
 * "0 available" next to it read as "nothing to book here".
 */
const shiftsLabel = computed(() => {
  const open = props.task.open_shifts ?? 0
  if (open > 0) return t('duties.tasks.quickView.openShifts', { count: open }, open)
  if (props.task.next_shift_date) return t('duties.tasks.quickView.allTaken')
  return t('duties.tasks.quickView.noUpcoming')
})

/** Same rule as the chips' (`WeekDayColumns`): no limit means room. */
function hasRoom(shift: DayShiftEntry): boolean {
  if (!shift.maxBookings) return true
  return (shift.currentBookings ?? 0) < shift.maxBookings
}

/**
 * The next shift worth showing, when the days on screen hold none (after the
 * hide-full filter, if it is on) and it lies beyond them. The strip stays on
 * the shared window by default, which lines the cards up by date; this lets
 * one card move there on request.
 */
const nextShiftBeyond = computed<string | null>(() => {
  const next = props.hideFullShifts ? props.task.next_open_shift_date : props.task.next_shift_date
  if (!next) return null
  const onScreen = days.value.some((day) =>
    day.shifts.some((s) => !props.hideFullShifts || hasRoom(s)),
  )
  if (onScreen) return null
  return next >= dateStr(rangeEnd.value) ? next : null // ISO dates compare lexicographically
})

const jumping = ref(false)

/**
 * Every card's button says "Show"; a screen reader also hears which task and
 * which day it moves to.
 */
const cardId = useId()
const nameId = `${cardId}-name`
const nextShiftId = `${cardId}-next-shift`

/** Move the strip to start on `date`; swiping back still reaches the days before. */
async function jumpTo(date: string) {
  if (jumping.value) return
  jumping.value = true
  const start = parseDate(date)
  if (await fetchDays(start, numDays.value)) {
    rangeStart.value = start
    rangeEnd.value = addDays(start, numDays.value)
  }
  jumping.value = false
}

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
            <h3 :id="nameId" class="text-sm font-semibold leading-tight line-clamp-2 break-words">
              {{ task.name }}
            </h3>
            <div v-if="canManage" class="flex shrink-0 items-center gap-1">
              <ShieldCheck class="h-3.5 w-3.5 text-primary" />
              <Badge :variant="statusVariant(task.status)" class="text-[10px]">
                {{ t(`duties.tasks.statuses.${task.status ?? 'draft'}`) }}
              </Badge>
            </div>
          </div>

          <!-- Reserved for a team: locked for the viewer, or just labelled -->
          <Badge
            v-if="task.team_name"
            variant="secondary"
            class="max-w-full text-[11px]"
            :data-testid="`task-team-badge-${task.id}`"
            :title="
              task.locked_by_team
                ? t('teamLocks.badge.locked', { name: task.team_name })
                : undefined
            "
          >
            <Lock v-if="task.locked_by_team" aria-hidden="true" />
            <UsersRound v-else aria-hidden="true" />
            <span class="truncate">
              {{
                task.locked_by_team
                  ? t('teamLocks.badge.only', { name: task.team_name })
                  : t('teamLocks.badge.team', { name: task.team_name })
              }}
            </span>
          </Badge>

          <Badge
            v-if="canManage && !canAdminEvent"
            variant="outline"
            class="text-[11px]"
            :data-testid="`task-in-charge-badge-${task.id}`"
          >
            <UserCheck aria-hidden="true" />
            {{ t('duties.tasks.managers.label') }}
          </Badge>

          <div
            v-if="(task.vouchers_per_shift ?? 0) > 0 || task.is_voucher_point"
            class="flex flex-wrap gap-1"
          >
            <Badge
              v-if="(task.vouchers_per_shift ?? 0) > 0"
              variant="secondary"
              class="text-[11px]"
              :data-testid="`task-vouchers-badge-${task.id}`"
            >
              <Ticket aria-hidden="true" />
              {{
                t(
                  'vouchers.task.perShift',
                  { n: task.vouchers_per_shift },
                  task.vouchers_per_shift ?? 0,
                )
              }}
            </Badge>
            <Badge
              v-if="task.is_voucher_point && task.status !== 'archived'"
              variant="outline"
              class="text-[11px]"
              :data-testid="`task-voucher-point-badge-${task.id}`"
            >
              <ScanLine aria-hidden="true" />
              {{ t('vouchers.task.point') }}
            </Badge>
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
          <TeamJoinButton
            v-if="task.locked_by_team && task.team_id && task.team_name"
            :event-id="task.event_id"
            :team-id="task.team_id"
            :team-name="task.team_name"
            :requires-approval="task.team_requires_approval ?? true"
            :my-status="task.my_team_status"
            variant="link"
            size="sm"
            class="h-auto min-w-0 justify-start px-0 text-xs font-semibold whitespace-normal text-left"
            @joined="emit('teamJoined')"
          />
          <span v-else class="text-xs text-muted-foreground" data-testid="task-row-shifts-label">
            {{ shiftsLabel }}
          </span>
          <HintTooltip v-if="canAdminEvent" :label="t('duties.tasks.delete')">
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
          :team-name="task.team_name"
          :book-before-start="(task.vouchers_per_shift ?? 0) > 0 && !canManage"
          :event-timezone="task.event_timezone"
          :has-more-next="hasMoreNext"
          :has-more-previous="hasMorePrevious"
          :loading-next="loadingNext"
          :loading-previous="loadingPrevious"
          @load-next="loadNext"
          @load-previous="loadPrevious"
          @click-shift="(slotId) => emit('clickShift', slotId, task)"
          @toggle-expand="expanded = !expanded"
        />
        <div
          v-if="nextShiftBeyond"
          class="mx-1 mt-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-md bg-muted/60 px-3 py-1.5 text-xs"
          data-testid="task-row-next-shift"
        >
          <span :id="nextShiftId" class="text-muted-foreground">
            {{ t('duties.tasks.quickView.nextShiftOn', { date: formatDateLabel(nextShiftBeyond) }) }}
          </span>
          <Button
            variant="outline"
            size="sm"
            class="h-11 px-3 text-xs sm:h-7 sm:px-2.5"
            :disabled="jumping"
            :aria-describedby="`${nameId} ${nextShiftId}`"
            data-testid="btn-task-row-jump"
            @click="jumpTo(nextShiftBeyond)"
          >
            {{ t('duties.tasks.quickView.jumpTo') }}
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>
