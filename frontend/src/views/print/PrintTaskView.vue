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
import VenueMiniMap from '@/components/venue-map/VenueMiniMap.vue'

import type {
  LocationDetailRead,
  ShiftBatchRead,
  ShiftListResponse,
  ShiftRead,
  TaskBookingEntry,
  TaskRead,
} from '@/client/types.gen'
import { formatDate } from '@/lib/format'
import { sharedLocationId } from '@/lib/venue-map'

const { t } = useI18n()
const { formatTime, formatDateLabel } = useFormatters()
const route = useRoute()
const { get } = useAuthenticatedClient()

const eventId = computed(() => route.params.eventId as string)

const task = ref<TaskRead | null>(null)
const allShifts = ref<ShiftRead[]>([])
const batches = ref<ShiftBatchRead[]>([])
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
const showMap = ref(true)

// === Venue map pin ===
// Same rule as the task details page: one location shared by every shift (or
// the task's own when it has no shifts yet). Several locations: no map.
const location = ref<LocationDetailRead | null>(null)
const miniMap = ref<InstanceType<typeof VenueMiniMap> | null>(null)
const pin = computed(() => location.value?.pins?.[0] ?? null)

const loadLocation = async () => {
  const locationId = sharedLocationId(allShifts.value, task.value?.location_id)
  if (!locationId) return
  try {
    const res = await get<{ data: LocationDetailRead }>({ url: `/locations/${locationId}` })
    location.value = res.data
  } catch {
    // Non-critical: the page prints without the map
  }
}

// All unique dates from shifts
const allDates = computed(() => [...new Set(allShifts.value.map((s) => s.date))].sort())

// Apply date filter
const shifts = computed(() => {
  return allShifts.value.filter((s) => selectedDates.value.has(s.date))
})

const eventUrl = computed(() => {
  return `${window.location.origin}/app/tasks/${eventId.value}`
})

const hasAnyLocation = computed(() => {
  return shifts.value.some((s) => s.location)
})

// Final visibility: user toggle controls the column
const showTitleColumn = computed(() => showTitle.value)
const showLocationColumn = computed(() => showLocation.value && hasAnyLocation.value)

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

interface BatchGroup {
  batch: ShiftBatchRead | null
  shifts: ShiftRead[]
}

const shiftsByBatch = computed<BatchGroup[]>(() => {
  if (batches.value.length <= 1) {
    return [{ batch: null, shifts: shifts.value }]
  }

  const batchMap = new Map<string, ShiftRead[]>()
  const unbatched: ShiftRead[] = []

  for (const shift of shifts.value) {
    if (shift.batch_id) {
      if (!batchMap.has(shift.batch_id)) batchMap.set(shift.batch_id, [])
      batchMap.get(shift.batch_id)!.push(shift)
    } else {
      unbatched.push(shift)
    }
  }

  const events: BatchGroup[] = []
  for (const batch of batches.value) {
    const shifts = batchMap.get(batch.id) ?? []
    if (shifts.length > 0) events.push({ batch, shifts })
  }
  if (unbatched.length > 0) events.push({ batch: null, shifts: unbatched })

  return events
})

const batchLabel = (batch: ShiftBatchRead) => {
  return batch.label || `${formatDate(batch.start_date)} – ${formatDate(batch.end_date)}`
}

const getBookingsForShift = (slotId: string): TaskBookingEntry[] => {
  return slotBookings.value.get(slotId) ?? []
}

/** Build sign-up lines for a shift: one row per max_bookings, pre-filled where booked */
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

// Lazy-load all bookings for the task in one request
const loadBookings = async () => {
  if (bookingsLoaded.value || bookingsLoading.value) return
  bookingsLoading.value = true
  try {
    const res = await get<{ data: TaskBookingEntry[] }>({
      url: `/tasks/${eventId.value}/bookings`,
    })
    const map = new Map<string, TaskBookingEntry[]>()
    for (const b of res.data) {
      if (!map.has(b.shift_id)) map.set(b.shift_id, [])
      map.get(b.shift_id)!.push(b)
    }
    slotBookings.value = map
  } catch {
    // Non-critical
  }
  bookingsLoaded.value = true
  bookingsLoading.value = false
}

const onToggleNames = async (val: boolean | 'indeterminate') => {
  includeNames.value = val === true
  if (val === true) await loadBookings()
}

// Track QR code readiness
let resolveQr: () => void
const qrReady = new Promise<void>((r) => {
  resolveQr = r
})
const onQrReady = () => resolveQr()

const handlePrint = async () => {
  if (includeNames.value) await loadBookings()
  await qrReady
  if (pin.value && showMap.value) {
    await nextTick()
    await miniMap.value?.ready()
  }
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
    const [eventRes, shiftsRes] = await Promise.all([
      get<{ data: TaskRead }>({ url: `/tasks/${eventId.value}` }),
      get<{ data: ShiftListResponse }>({
        url: '/shifts/',
        query: { task_id: eventId.value, limit: 200 },
      }),
    ])
    task.value = eventRes.data
    allShifts.value = shiftsRes.data.items

    // Select all dates by default
    selectedDates.value = new Set(allShifts.value.map((s) => s.date))

    // Set default visibility based on whether values vary
    showTitle.value = new Set(shiftsRes.data.items.map((s: ShiftRead) => s.title)).size > 1
    showLocation.value =
      new Set(shiftsRes.data.items.map((s: ShiftRead) => s.location).filter(Boolean)).size > 1

    try {
      const batchRes = await get<{ data: ShiftBatchRead[] }>({
        url: `/tasks/${eventId.value}/batches`,
      })
      batches.value = batchRes.data
    } catch {
      // Non-critical
    }

    await loadLocation()
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
      <label v-if="pin" class="flex items-center gap-2 cursor-pointer">
        <Checkbox v-model="showMap" data-testid="print-toggle-map" />
        <span class="text-sm">{{ t('print.toolbar.showMap') }}</span>
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
        <label v-for="date in allDates" :key="date" class="flex items-center gap-2 cursor-pointer">
          <Checkbox
            :model-value="selectedDates.has(date)"
            @update:model-value="(val: boolean | 'indeterminate') => toggleDate(date, val)"
          />
          <span class="text-xs">{{
            formatDateLabel(date, { weekday: 'short', month: 'short', day: 'numeric' })
          }}</span>
        </label>
      </div>
    </PrintToolbar>

    <div v-if="loading" class="py-12 text-center text-muted-foreground">
      {{ t('common.states.loading') }}
    </div>

    <template v-else-if="task">
      <!--
        Wrap everything in one <table> so the browser can repeat the <thead>
        (task header + column headers) on every printed page.
      -->
      <table data-testid="print-content" class="w-full border-collapse">
        <thead :class="repeatHeader ? 'print-repeat-header' : ''">
          <tr>
            <th class="text-left font-normal p-0 pb-4">
              <!-- QR Code + Header -->
              <div class="flex items-start justify-between gap-4">
                <div class="space-y-2 flex-1">
                  <h1 class="text-3xl font-bold">{{ task.name }}</h1>
                  <p v-if="task.description" class="text-muted-foreground text-lg">
                    {{ task.description }}
                  </p>
                  <div
                    class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground"
                  >
                    <span class="flex items-center gap-1">
                      <CalendarDays class="h-4 w-4" />
                      {{ formatDate(task.start_date) }} – {{ formatDate(task.end_date) }}
                    </span>
                    <span v-if="task.location" class="flex items-center gap-1">
                      <MapPin class="h-4 w-4" />
                      {{ task.location }}
                    </span>
                    <span v-if="task.category" class="flex items-center gap-1">
                      <Tag class="h-4 w-4" />
                      {{ task.category }}
                    </span>
                  </div>
                </div>
                <div class="shrink-0 text-center space-y-1">
                  <QrCode :value="eventUrl" :size="96" @ready="onQrReady" />
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
              <!--
                Where it is. Below the header rather than in it, so a repeated
                header does not print the map again on every page.
              -->
              <div
                v-if="pin && showMap && task.event_id"
                class="mb-4 max-w-md print-keep-together"
                data-testid="print-mini-map"
              >
                <VenueMiniMap
                  ref="miniMap"
                  :event-id="task.event_id"
                  :pin="pin"
                  :link-to-map="false"
                  static
                />
              </div>
              <!-- Duty Shifts -->
              <div v-if="shifts.length > 0" class="space-y-4">
                <div
                  v-for="event in shiftsByBatch"
                  :key="event.batch?.id ?? 'all'"
                  class="space-y-3"
                >
                  <h3 v-if="event.batch" class="font-semibold text-lg">
                    {{ batchLabel(event.batch) }}
                    <span
                      v-if="event.batch.location"
                      class="text-sm font-normal text-muted-foreground ml-2"
                    >
                      {{ event.batch.location }}
                    </span>
                  </h3>

                  <div
                    v-for="[date, shifts] in groupByDate(event.shifts)"
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
                          <th v-if="showTitleColumn" class="py-1 px-1 font-medium">
                            {{ t('duties.shifts.fields.title') }}
                          </th>
                          <th v-if="showLocationColumn" class="py-1 px-1 font-medium">
                            {{ t('duties.shifts.fields.location') }}
                          </th>
                          <th class="py-1 px-1 font-medium w-[35%]">{{ t('print.nameColumn') }}</th>
                          <th class="py-1 px-1 font-medium w-[25%]">
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
                              v-if="showTitleColumn && lineIdx === 0"
                              :rowspan="getShiftLines(shift).length"
                              class="py-1 px-1 border-r border-dashed"
                            >
                              {{ shift.title }}
                            </td>
                            <td
                              v-if="showLocationColumn && lineIdx === 0"
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
                                <div class="border-b border-dotted border-foreground/30 h-5"></div>
                              </template>
                            </td>
                            <td class="py-1 px-1">
                              <template v-if="line.contact">
                                <span>{{ line.contact }}</span>
                              </template>
                              <template v-else>
                                <div class="border-b border-dotted border-foreground/30 h-5"></div>
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
</template>
