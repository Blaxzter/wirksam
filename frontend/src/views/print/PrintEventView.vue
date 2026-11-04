<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'

import { CalendarDays, MapPin, Tag } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useFormatters } from '@/composables/useFormatters'

import { Checkbox } from '@/components/ui/checkbox'

import PrintToolbar from '@/components/print/PrintToolbar.vue'
import QrCode from '@/components/print/QrCode.vue'

import type {
  ShiftListResponse,
  ShiftRead,
  TaskBookingEntry,
  EventRead,
  TaskListResponse,
  TaskRead,
  ShiftBatchRead,
} from '@/client/types.gen'
import { formatDate } from '@/lib/format'

const { t } = useI18n()
const { formatTime, formatDateLabel } = useFormatters()
const route = useRoute()
const { get } = useAuthenticatedClient()

const eventId = computed(() => route.params.eventId as string)
const mode = computed(() => (route.query.mode as string) ?? 'overview')

const event = ref<EventRead | null>(null)
const tasks = ref<TaskRead[]>([])
const rawTaskShifts = ref<Map<string, ShiftRead[]>>(new Map())
const eventBatches = ref<Map<string, ShiftBatchRead[]>>(new Map())
const slotBookings = ref<Map<string, TaskBookingEntry[]>>(new Map())
const loading = ref(true)
const bookingsLoaded = ref(false)
const bookingsLoading = ref(false)

// Display options (toolbar toggles)
const showTitle = ref(true)
const showLocation = ref(true)
const repeatHeader = ref(true)
const includeNames = ref(false)
const selectedDates = ref<Set<string>>(new Set())

// All unique dates across all task shifts
const allDates = computed(() => {
  const dates = new Set<string>()
  for (const shifts of rawTaskShifts.value.values()) {
    for (const s of shifts) dates.add(s.date)
  }
  return [...dates].sort()
})

// Apply date filter to per-task shifts
const eventShifts = computed(() => {
  const filtered = new Map<string, ShiftRead[]>()
  for (const [evId, shifts] of rawTaskShifts.value) {
    filtered.set(
      evId,
      shifts.filter((s) => selectedDates.value.has(s.date)),
    )
  }
  return filtered
})

const groupUrl = computed(() => {
  return `${window.location.origin}/app/events/${eventId.value}`
})

const eventUrl = (eventId: string) => {
  return `${window.location.origin}/app/tasks/${eventId}`
}

// Per-task column checks — user toggle controls visibility
const eventShowTitleColumn = () => showTitle.value
const eventHasLocationData = (eventId: string) => {
  const shifts = eventShifts.value.get(eventId) ?? []
  return shifts.some((s) => s.location)
}
const eventShowLocationColumn = (eventId: string) => {
  return showLocation.value && eventHasLocationData(eventId)
}

/**
 * Phone numbers come only for organisers and the task's people in charge.
 * Anyone else printing the names would get a column of blank lines that looks
 * like it wants filling in, so it goes; a blank sign-up sheet keeps it.
 */
const eventShowContactColumn = (task: TaskRead) =>
  !includeNames.value ||
  !!task.can_manage ||
  (eventShifts.value.get(task.id) ?? []).some((s) =>
    getBookingsForShift(s.id).some((b) => b.user_phone_number),
  )

interface BatchGroup {
  batch: ShiftBatchRead | null
  shifts: ShiftRead[]
}

const getShiftsByBatch = (eventId: string): BatchGroup[] => {
  const shifts = eventShifts.value.get(eventId) ?? []
  const batchList = eventBatches.value.get(eventId) ?? []

  if (batchList.length <= 1) {
    return [{ batch: null, shifts }]
  }

  const batchMap = new Map<string, ShiftRead[]>()
  const unbatched: ShiftRead[] = []

  for (const shift of shifts) {
    if (shift.batch_id) {
      if (!batchMap.has(shift.batch_id)) batchMap.set(shift.batch_id, [])
      batchMap.get(shift.batch_id)!.push(shift)
    } else {
      unbatched.push(shift)
    }
  }

  const events: BatchGroup[] = []
  for (const batch of batchList) {
    const batchShifts = batchMap.get(batch.id) ?? []
    if (batchShifts.length > 0) events.push({ batch, shifts: batchShifts })
  }
  if (unbatched.length > 0) events.push({ batch: null, shifts: unbatched })

  return events
}

const groupByDate = (shifts: ShiftRead[]) => {
  const events: Record<string, ShiftRead[]> = {}
  for (const shift of shifts) {
    if (!events[shift.date]) events[shift.date] = []
    events[shift.date].push(shift)
  }
  for (const dateShifts of Object.values(events)) {
    dateShifts.sort(
      (a, b) =>
        (a.start_time ?? '').localeCompare(b.start_time ?? '') ||
        (a.end_time ?? '').localeCompare(b.end_time ?? ''),
    )
  }
  return Object.entries(events).sort(([a], [b]) => a.localeCompare(b))
}

const batchLabel = (batch: ShiftBatchRead) => {
  return batch.label || `${formatDate(batch.start_date)} – ${formatDate(batch.end_date)}`
}

const getBookingsForShift = (slotId: string): TaskBookingEntry[] => {
  return slotBookings.value.get(slotId) ?? []
}

const getShiftLines = (shift: ShiftRead) => {
  const max = shift.max_bookings ?? 1
  const bookings = getBookingsForShift(shift.id)
  const lines: { name: string; contact: string }[] = []
  for (let i = 0; i < max; i++) {
    const b = bookings[i]
    lines.push({
      name: b?.user_name ?? '',
      contact: b?.user_phone_number ?? '',
    })
  }
  return lines
}

// Lazy-load all bookings for all tasks in one request per task
const loadBookings = async () => {
  if (bookingsLoaded.value || bookingsLoading.value) return
  bookingsLoading.value = true
  try {
    const promises = tasks.value.map(async (ev) => {
      try {
        const res = await get<{ data: TaskBookingEntry[] }>({
          url: `/tasks/${ev.id}/bookings`,
        })
        for (const b of res.data) {
          if (!slotBookings.value.has(b.shift_id)) slotBookings.value.set(b.shift_id, [])
          slotBookings.value.get(b.shift_id)!.push(b)
        }
      } catch {
        // Non-critical
      }
    })
    await Promise.all(promises)
  } finally {
    bookingsLoaded.value = true
    bookingsLoading.value = false
  }
}

const onToggleNames = async (val: boolean | 'indeterminate') => {
  includeNames.value = val === true
  if (val === true) await loadBookings()
}

// Track QR code readiness
const expectedQrCount = ref(1)
let qrReadyCount = 0
let resolveAllQr: () => void
const allQrReady = new Promise<void>((r) => {
  resolveAllQr = r
})
const onQrReady = () => {
  qrReadyCount++
  if (qrReadyCount >= expectedQrCount.value) resolveAllQr()
}

const handlePrint = async () => {
  if (includeNames.value) await loadBookings()
  expectedQrCount.value = mode.value === 'all' ? Math.max(tasks.value.length, 1) : 1
  await allQrReady
  await nextTick()
  await new Promise((r) => setTimeout(r, 300))
  window.print()
}

// Date filter helpers
const allDatesSelected = computed(() => selectedDates.value.size === allDates.value.length)
const noneDatesSelected = computed(() => selectedDates.value.size === 0)

const toggleAllDates = () => {
  selectedDates.value = allDatesSelected.value ? new Set() : new Set(allDates.value)
}
const toggleDate = (date: string, checked: boolean | 'indeterminate') => {
  const next = new Set(selectedDates.value)
  if (checked === true) next.add(date)
  else next.delete(date)
  selectedDates.value = next
}

onMounted(async () => {
  try {
    const [groupRes, tasksRes] = await Promise.all([
      get<{ data: EventRead }>({ url: `/events/${eventId.value}` }),
      get<{ data: TaskListResponse }>({
        url: '/tasks/',
        query: { limit: 200, event_id: eventId.value },
      }),
    ])
    event.value = groupRes.data
    tasks.value = tasksRes.data.items.sort((a: TaskRead, b: TaskRead) =>
      a.start_date.localeCompare(b.start_date),
    )

    if (mode.value === 'all') {
      const slotPromises = tasks.value.map(async (ev) => {
        try {
          const res = await get<{ data: ShiftListResponse }>({
            url: '/shifts/',
            query: { task_id: ev.id, limit: 200 },
          })
          rawTaskShifts.value.set(ev.id, res.data.items)
        } catch {
          rawTaskShifts.value.set(ev.id, [])
        }
      })
      const batchPromises = tasks.value.map(async (ev) => {
        try {
          const res = await get<{ data: ShiftBatchRead[] }>({
            url: `/tasks/${ev.id}/batches`,
          })
          eventBatches.value.set(ev.id, res.data)
        } catch {
          eventBatches.value.set(ev.id, [])
        }
      })
      await Promise.all([...slotPromises, ...batchPromises])

      // Select all dates by default
      const allShiftItems = tasks.value.flatMap((ev) => rawTaskShifts.value.get(ev.id) ?? [])
      selectedDates.value = new Set(allShiftItems.map((s) => s.date))

      // Set default visibility based on whether values vary
      showTitle.value = new Set(allShiftItems.map((s) => s.title)).size > 1
      showLocation.value = new Set(allShiftItems.map((s) => s.location).filter(Boolean)).size > 1
    }
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="print-page mx-auto max-w-5xl w-full space-y-4 p-4 print:p-0">
    <!-- Floating toolbar -->
    <PrintToolbar
      data-testid="print-toolbar"
      :disabled="loading || bookingsLoading"
      @print="handlePrint"
    >
      <template v-if="mode === 'all'">
        <!-- Column toggles -->
        <label class="flex items-center gap-2 cursor-pointer">
          <Checkbox v-model="showTitle" />
          <span class="text-sm">{{ t('print.toolbar.showTitle') }}</span>
        </label>
        <label class="flex items-center gap-2 cursor-pointer">
          <Checkbox v-model="showLocation" />
          <span class="text-sm">{{ t('print.toolbar.showLocation') }}</span>
        </label>
        <label class="flex items-center gap-2 cursor-pointer">
          <Checkbox v-model="repeatHeader" />
          <span class="text-sm">{{ t('print.toolbar.repeatHeader') }}</span>
        </label>

        <!-- Include names -->
        <div class="border-t pt-2 mt-1">
          <label class="flex items-center gap-2 cursor-pointer">
            <Checkbox :model-value="includeNames" @update:model-value="onToggleNames" />
            <span class="text-sm">{{ t('print.toolbar.includeNames') }}</span>
          </label>
          <p v-if="bookingsLoading" class="text-xs text-muted-foreground mt-1">
            {{ t('common.states.loading') }}
          </p>
        </div>

        <!-- Date filter -->
        <div v-if="allDates.length > 1" class="border-t pt-2 mt-1 space-y-1">
          <span class="text-xs font-medium text-muted-foreground">{{
            t('print.toolbar.filterDates')
          }}</span>
          <label class="flex items-center gap-2 cursor-pointer">
            <Checkbox
              :model-value="allDatesSelected ? true : noneDatesSelected ? false : 'indeterminate'"
              @update:model-value="toggleAllDates"
            />
            <span class="text-xs">{{ t('print.optionsDialog.selectAll') }}</span>
          </label>
          <label
            v-for="date in allDates"
            :key="date"
            class="flex items-center gap-2 cursor-pointer"
          >
            <Checkbox
              :model-value="selectedDates.has(date)"
              @update:model-value="(val: boolean | 'indeterminate') => toggleDate(date, val)"
            />
            <span class="text-xs">{{
              formatDateLabel(date, { weekday: 'short', month: 'short', day: 'numeric' })
            }}</span>
          </label>
        </div>
      </template>
    </PrintToolbar>

    <div v-if="loading" class="py-12 text-center text-muted-foreground">
      {{ t('common.states.loading') }}
    </div>

    <div v-else-if="event" data-testid="print-content">
      <!-- ======================== OVERVIEW MODE ======================== -->
      <template v-if="mode === 'overview'">
        <div class="flex items-start justify-between gap-4">
          <div class="space-y-2 flex-1">
            <h1 class="text-3xl font-bold">{{ event.name }}</h1>
            <p v-if="event.description" class="text-muted-foreground text-lg">
              {{ event.description }}
            </p>
            <p class="text-sm text-muted-foreground flex items-center gap-1">
              <CalendarDays class="h-4 w-4" />
              {{ formatDate(event.start_date) }} – {{ formatDate(event.end_date) }}
            </p>
          </div>
          <div class="shrink-0 text-center space-y-1">
            <QrCode :value="groupUrl" :size="96" @ready="onQrReady" />
            <p class="text-xs text-muted-foreground">{{ t('print.scanToSignUp') }}</p>
          </div>
        </div>

        <hr class="border-foreground/20" />

        <div class="space-y-4">
          <h2 class="text-xl font-semibold">{{ t('duties.events.detail.tasks') }}</h2>

          <div v-if="tasks.length === 0" class="text-muted-foreground text-sm">
            {{ t('duties.events.detail.tasksEmpty') }}
          </div>

          <div v-else class="space-y-3">
            <div
              v-for="ev in tasks"
              :key="ev.id"
              class="rounded-lg border p-4 space-y-1 print-keep-together"
            >
              <h3 class="font-semibold text-lg">{{ ev.name }}</h3>
              <p v-if="ev.description" class="text-sm text-muted-foreground">
                {{ ev.description }}
              </p>
              <div
                class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground"
              >
                <span class="flex items-center gap-1">
                  <CalendarDays class="h-3.5 w-3.5" />
                  {{ formatDate(ev.start_date) }} – {{ formatDate(ev.end_date) }}
                </span>
                <span v-if="ev.location" class="flex items-center gap-1">
                  <MapPin class="h-3.5 w-3.5" />
                  {{ ev.location }}
                </span>
                <span v-if="ev.category" class="flex items-center gap-1">
                  <Tag class="h-3.5 w-3.5" />
                  {{ ev.category }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- ======================== ALL EVENTS MODE ======================== -->
      <template v-else>
        <table
          v-for="(ev, evIdx) in tasks"
          :key="ev.id"
          :class="{ 'print-page-break': evIdx > 0 }"
          class="w-full border-collapse"
        >
          <thead :class="repeatHeader ? 'print-repeat-header' : ''">
            <tr>
              <th class="text-left font-normal p-0 pb-4">
                <div class="flex items-start justify-between gap-4">
                  <div class="space-y-2 flex-1">
                    <p class="text-sm text-muted-foreground">{{ event.name }}</p>
                    <h1 class="text-3xl font-bold">{{ ev.name }}</h1>
                    <p v-if="ev.description" class="text-muted-foreground text-lg">
                      {{ ev.description }}
                    </p>
                    <div
                      class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground"
                    >
                      <span class="flex items-center gap-1">
                        <CalendarDays class="h-4 w-4" />
                        {{ formatDate(ev.start_date) }} – {{ formatDate(ev.end_date) }}
                      </span>
                      <span v-if="ev.location" class="flex items-center gap-1">
                        <MapPin class="h-4 w-4" />
                        {{ ev.location }}
                      </span>
                      <span v-if="ev.category" class="flex items-center gap-1">
                        <Tag class="h-4 w-4" />
                        {{ ev.category }}
                      </span>
                    </div>
                  </div>
                  <div class="shrink-0 text-center space-y-1">
                    <QrCode :value="eventUrl(ev.id)" :size="96" @ready="onQrReady" />
                    <p class="text-xs text-muted-foreground">{{ t('print.scanToSignUp') }}</p>
                  </div>
                </div>
                <hr class="border-foreground/20 mt-4" />
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td class="p-0">
                <div v-if="(eventShifts.get(ev.id) ?? []).length > 0" class="space-y-4">
                  <div
                    v-for="batchGroup in getShiftsByBatch(ev.id)"
                    :key="batchGroup.batch?.id ?? 'all'"
                    class="space-y-3"
                  >
                    <h3 v-if="batchGroup.batch" class="font-semibold text-lg">
                      {{ batchLabel(batchGroup.batch) }}
                      <span
                        v-if="batchGroup.batch.location"
                        class="text-sm font-normal text-muted-foreground ml-2"
                      >
                        {{ batchGroup.batch.location }}
                      </span>
                    </h3>

                    <div
                      v-for="[date, shifts] in groupByDate(batchGroup.shifts)"
                      :key="date"
                      class="space-y-1 print-keep-together"
                    >
                      <h4 class="font-medium text-sm bg-muted px-2 py-1 rounded print-bg">
                        {{
                          formatDateLabel(date, {
                            weekday: 'long',
                            year: 'numeric',
                            month: 'long',
                            day: 'numeric',
                          })
                        }}
                      </h4>
                      <table class="w-full text-sm border-collapse">
                        <thead>
                          <tr class="border-b text-left">
                            <th class="py-1 px-1 font-medium w-20">
                              {{ t('duties.shifts.fields.startTime') }}
                            </th>
                            <th class="py-1 px-1 font-medium w-20">
                              {{ t('duties.shifts.fields.endTime') }}
                            </th>
                            <th v-if="eventShowTitleColumn()" class="py-1 px-1 font-medium">
                              {{ t('duties.shifts.fields.title') }}
                            </th>
                            <th v-if="eventShowLocationColumn(ev.id)" class="py-1 px-1 font-medium">
                              {{ t('duties.shifts.fields.location') }}
                            </th>
                            <th class="py-1 px-1 font-medium w-[35%]">
                              {{ t('print.nameColumn') }}
                            </th>
                            <th
                              v-if="eventShowContactColumn(ev)"
                              class="py-1 px-1 font-medium w-[25%]"
                            >
                              {{ t('print.contactColumn') }}
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          <template v-for="shift in shifts" :key="shift.id">
                            <tr
                              v-for="(line, lineIdx) in getShiftLines(shift)"
                              :key="`${shift.id}-${lineIdx}`"
                              class="border-b border-dashed align-top"
                            >
                              <td
                                v-if="lineIdx === 0"
                                :rowspan="getShiftLines(shift).length"
                                class="py-1 px-1 font-mono border-r border-dashed"
                              >
                                {{ formatTime(shift.start_time) || '—' }}
                              </td>
                              <td
                                v-if="lineIdx === 0"
                                :rowspan="getShiftLines(shift).length"
                                class="py-1 px-1 font-mono border-r border-dashed"
                              >
                                {{ formatTime(shift.end_time) || '—' }}
                              </td>
                              <td
                                v-if="eventShowTitleColumn() && lineIdx === 0"
                                :rowspan="getShiftLines(shift).length"
                                class="py-1 px-1 border-r border-dashed"
                              >
                                {{ shift.title }}
                              </td>
                              <td
                                v-if="eventShowLocationColumn(ev.id) && lineIdx === 0"
                                :rowspan="getShiftLines(shift).length"
                                class="py-1 px-1 border-r border-dashed"
                              >
                                {{ shift.location ?? '' }}
                              </td>
                              <td class="py-1 px-1">
                                <template v-if="line.name">
                                  <span class="font-medium">{{ line.name }}</span>
                                </template>
                                <template v-else>
                                  <div
                                    class="border-b border-dotted border-foreground/30 h-5"
                                  ></div>
                                </template>
                              </td>
                              <td v-if="eventShowContactColumn(ev)" class="py-1 px-1">
                                <template v-if="line.contact">
                                  <span>{{ line.contact }}</span>
                                </template>
                                <template v-else>
                                  <div
                                    class="border-b border-dotted border-foreground/30 h-5"
                                  ></div>
                                </template>
                              </td>
                            </tr>
                          </template>
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </template>
    </div>
  </div>
</template>
