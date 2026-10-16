<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { MapPin, ShieldCheck, Tag, Trash2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import HintTooltip from '@/components/utils/HintTooltip.vue'

import type { FeedTaskItem, FeedShiftEntry, ShiftWindowResponse } from '@/client/types.gen'
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
const weekOffset = ref(0)
const expanded = ref(false)
const loadingWindow = ref(false)

// Cache of fetched shift windows keyed by "YYYY-MM-DD" start date
const slotCache = ref<Map<string, FeedShiftEntry[]>>(new Map())

// Window start date from feed (initial window)
const initialWindowStart = computed(() => {
  if (props.task.slot_window_start) {
    const [y, m, d] = props.task.slot_window_start.split('-').map(Number)
    return new Date(y, m - 1, d)
  }
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return today
})

const startDate = computed(() => {
  const d = new Date(initialWindowStart.value)
  d.setDate(d.getDate() + weekOffset.value * numDays.value)
  return d
})

function dateStr(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function feedShiftsToDay(shifts: FeedShiftEntry[]): Map<string, DayShiftEntry[]> {
  const map = new Map<string, DayShiftEntry[]>()
  for (const shift of shifts) {
    const key = shift.date
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push({
      slotId: shift.id,
      startTime: shift.start_time,
      endTime: shift.end_time,
      currentBookings: shift.current_bookings,
      maxBookings: shift.max_bookings,
      isBookedByMe: shift.is_booked_by_me,
      collidesWithMyBooking: shift.collides_with_my_booking,
    })
  }
  return map
}

// Get the active shifts for the current window (from cache or initial feed)
const activeShifts = computed<FeedShiftEntry[]>(() => {
  const key = dateStr(startDate.value)
  // Check cache first
  if (slotCache.value.has(key)) {
    return slotCache.value.get(key)!
  }
  // If offset is 0, use the initial feed data
  if (weekOffset.value === 0) {
    return props.task.shifts ?? []
  }
  // No data yet for this window
  return []
})

const days = computed<DayColumn[]>(() => {
  const shiftsByDate = feedShiftsToDay(activeShifts.value)
  const result: DayColumn[] = []

  for (let i = 0; i < numDays.value; i++) {
    const date = new Date(startDate.value)
    date.setDate(date.getDate() + i)
    const ds = dateStr(date)
    const dayShifts = shiftsByDate.get(ds) ?? []
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

// Fetch a shift window for a given start date
async function fetchShiftWindow(start: Date) {
  const key = dateStr(start)
  if (slotCache.value.has(key)) return
  loadingWindow.value = true
  try {
    const res = await get<{ data: ShiftWindowResponse }>({
      url: `/tasks/${props.task.id}/shift-window`,
      query: { start_date: key, days: numDays.value },
    })
    const newCache = new Map(slotCache.value)
    newCache.set(key, res.data.shifts)
    slotCache.value = newCache
  } catch (error) {
    toastApiError(error)
  } finally {
    loadingWindow.value = false
  }
}

// When weekOffset changes and we don't have data, fetch
watch(weekOffset, () => {
  if (weekOffset.value === 0) return // initial data from feed
  const key = dateStr(startDate.value)
  if (!slotCache.value.has(key)) {
    fetchShiftWindow(startDate.value)
  }
})

// Reset cache when the task changes (e.g. feed re-fetched)
watch(
  () => props.task.id,
  () => {
    slotCache.value = new Map()
    weekOffset.value = 0
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

          <p
            v-if="task.description"
            class="text-xs text-muted-foreground line-clamp-2 break-words"
          >
            {{ task.description }}
          </p>

          <div class="space-y-1">
            <div
              v-if="task.location"
              class="flex items-center gap-1 text-xs text-muted-foreground"
            >
              <MapPin class="h-3 w-3 shrink-0" />
              <span class="truncate">{{ task.location }}</span>
            </div>
            <div
              v-if="task.category"
              class="flex items-center gap-1 text-xs text-muted-foreground"
            >
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
          @previous="weekOffset--"
          @next="weekOffset++"
          @click-shift="(slotId) => emit('clickShift', slotId, task)"
          @toggle-expand="expanded = !expanded"
        />
      </div>
    </div>
  </div>
</template>
