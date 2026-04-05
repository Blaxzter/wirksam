<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'

import { CalendarDays, MapPin, Tag } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useFormatters } from '@/composables/useFormatters'

import { Checkbox } from '@/components/ui/checkbox'

import PrintToolbar from '@/components/print/PrintToolbar.vue'
import QrCode from '@/components/print/QrCode.vue'

import type {
  DutySlotListResponse,
  DutySlotRead,
  EventBookingEntry,
  EventRead,
  SlotBatchRead,
} from '@/client/types.gen'
import { formatDate } from '@/lib/format'

const { t } = useI18n()
const { formatTime, formatDateLabel } = useFormatters()
const route = useRoute()
const { get } = useAuthenticatedClient()

const eventId = computed(() => route.params.eventId as string)

const event = ref<EventRead | null>(null)
const allDutySlots = ref<DutySlotRead[]>([])
const batches = ref<SlotBatchRead[]>([])
const slotBookings = ref<Map<string, EventBookingEntry[]>>(new Map())
const loading = ref(true)
const bookingsLoaded = ref(false)
const bookingsLoading = ref(false)

// Display options (toolbar toggles)
const showTitle = ref(true)
const showLocation = ref(true)
const repeatHeader = ref(true)
const includeNames = ref(false)
const selectedDates = ref<Set<string>>(new Set())

// All unique dates from slots
const allDates = computed(() => [...new Set(allDutySlots.value.map((s) => s.date))].sort())

// Apply date filter
const dutySlots = computed(() => {
  return allDutySlots.value.filter((s) => selectedDates.value.has(s.date))
})

const eventUrl = computed(() => {
  return `${window.location.origin}/app/events/${eventId.value}`
})

// Check if column would have varied content
const hasMultipleTitles = computed(() => {
  return new Set(dutySlots.value.map((s) => s.title)).size > 1
})
const hasAnyLocation = computed(() => {
  return dutySlots.value.some((s) => s.location)
})
const hasMultipleLocations = computed(() => {
  return new Set(dutySlots.value.map((s) => s.location).filter(Boolean)).size > 1
})

// Final visibility: user toggle controls the column
const showTitleColumn = computed(() => showTitle.value)
const showLocationColumn = computed(() => showLocation.value && hasAnyLocation.value)

const groupByDate = (slots: DutySlotRead[]) => {
  const groups: Record<string, DutySlotRead[]> = {}
  for (const slot of slots) {
    if (!groups[slot.date]) groups[slot.date] = []
    groups[slot.date].push(slot)
  }
  for (const dateSlots of Object.values(groups)) {
    dateSlots.sort(
      (a, b) =>
        (a.start_time ?? '').localeCompare(b.start_time ?? '') ||
        (a.end_time ?? '').localeCompare(b.end_time ?? ''),
    )
  }
  return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b))
}

interface BatchGroup {
  batch: SlotBatchRead | null
  slots: DutySlotRead[]
}

const slotsByBatch = computed<BatchGroup[]>(() => {
  if (batches.value.length <= 1) {
    return [{ batch: null, slots: dutySlots.value }]
  }

  const batchMap = new Map<string, DutySlotRead[]>()
  const unbatched: DutySlotRead[] = []

  for (const slot of dutySlots.value) {
    if (slot.batch_id) {
      if (!batchMap.has(slot.batch_id)) batchMap.set(slot.batch_id, [])
      batchMap.get(slot.batch_id)!.push(slot)
    } else {
      unbatched.push(slot)
    }
  }

  const groups: BatchGroup[] = []
  for (const batch of batches.value) {
    const slots = batchMap.get(batch.id) ?? []
    if (slots.length > 0) groups.push({ batch, slots })
  }
  if (unbatched.length > 0) groups.push({ batch: null, slots: unbatched })

  return groups
})

const batchLabel = (batch: SlotBatchRead) => {
  return batch.label || `${formatDate(batch.start_date)} – ${formatDate(batch.end_date)}`
}

const getBookingsForSlot = (slotId: string): EventBookingEntry[] => {
  return slotBookings.value.get(slotId) ?? []
}

/** Build sign-up lines for a slot: one row per max_bookings, pre-filled where booked */
const getSlotLines = (slot: DutySlotRead) => {
  const max = slot.max_bookings ?? 1
  const bookings = getBookingsForSlot(slot.id)
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

// Lazy-load all bookings for the event in one request
const loadBookings = async () => {
  if (bookingsLoaded.value || bookingsLoading.value) return
  bookingsLoading.value = true
  try {
    const res = await get<{ data: EventBookingEntry[] }>({
      url: `/events/${eventId.value}/bookings`,
    })
    const map = new Map<string, EventBookingEntry[]>()
    for (const b of res.data) {
      if (!map.has(b.duty_slot_id)) map.set(b.duty_slot_id, [])
      map.get(b.duty_slot_id)!.push(b)
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
    const [eventRes, slotsRes] = await Promise.all([
      get<{ data: EventRead }>({ url: `/events/${eventId.value}` }),
      get<{ data: DutySlotListResponse }>({
        url: '/duty-slots/',
        query: { event_id: eventId.value, limit: 200 },
      }),
    ])
    event.value = eventRes.data
    allDutySlots.value = slotsRes.data.items

    // Select all dates by default
    selectedDates.value = new Set(allDutySlots.value.map((s) => s.date))

    // Set default visibility based on whether values vary
    showTitle.value = new Set(slotsRes.data.items.map((s: DutySlotRead) => s.title)).size > 1
    showLocation.value =
      new Set(slotsRes.data.items.map((s: DutySlotRead) => s.location).filter(Boolean)).size > 1

    try {
      const batchRes = await get<{ data: SlotBatchRead[] }>({
        url: `/events/${eventId.value}/batches`,
      })
      batches.value = batchRes.data
    } catch {
      // Non-critical
    }
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="print-page mx-auto max-w-5xl w-full space-y-4 p-4 print:p-0">
    <!-- Floating toolbar -->
    <PrintToolbar data-testid="print-toolbar" :disabled="loading || bookingsLoading" @print="handlePrint">
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

    <template v-else-if="event">
      <!--
        Wrap everything in one <table> so the browser can repeat the <thead>
        (event header + column headers) on every printed page.
      -->
      <table data-testid="print-content" class="w-full border-collapse">
        <thead :class="repeatHeader ? 'print-repeat-header' : ''">
          <tr>
            <th class="text-left font-normal p-0 pb-4">
              <!-- QR Code + Header -->
              <div class="flex items-start justify-between gap-4">
                <div class="space-y-2 flex-1">
                  <h1 class="text-3xl font-bold">{{ event.name }}</h1>
                  <p v-if="event.description" class="text-muted-foreground text-lg">
                    {{ event.description }}
                  </p>
                  <div
                    class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground"
                  >
                    <span class="flex items-center gap-1">
                      <CalendarDays class="h-4 w-4" />
                      {{ formatDate(event.start_date) }} – {{ formatDate(event.end_date) }}
                    </span>
                    <span v-if="event.location" class="flex items-center gap-1">
                      <MapPin class="h-4 w-4" />
                      {{ event.location }}
                    </span>
                    <span v-if="event.category" class="flex items-center gap-1">
                      <Tag class="h-4 w-4" />
                      {{ event.category }}
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
              <!-- Duty Slots -->
              <div v-if="dutySlots.length > 0" class="space-y-4">
                <div
                  v-for="group in slotsByBatch"
                  :key="group.batch?.id ?? 'all'"
                  class="space-y-3"
                >
                  <h3 v-if="group.batch" class="font-semibold text-lg">
                    {{ batchLabel(group.batch) }}
                    <span
                      v-if="group.batch.location"
                      class="text-sm font-normal text-muted-foreground ml-2"
                    >
                      {{ group.batch.location }}
                    </span>
                  </h3>

                  <div
                    v-for="[date, slots] in groupByDate(group.slots)"
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
                            {{ t('duties.dutySlots.fields.startTime') }}
                          </th>
                          <th class="py-1 px-1 font-medium w-20">
                            {{ t('duties.dutySlots.fields.endTime') }}
                          </th>
                          <th v-if="showTitleColumn" class="py-1 px-1 font-medium">
                            {{ t('duties.dutySlots.fields.title') }}
                          </th>
                          <th v-if="showLocationColumn" class="py-1 px-1 font-medium">
                            {{ t('duties.dutySlots.fields.location') }}
                          </th>
                          <th class="py-1 px-1 font-medium w-[35%]">{{ t('print.nameColumn') }}</th>
                          <th class="py-1 px-1 font-medium w-[25%]">
                            {{ t('print.contactColumn') }}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        <template v-for="slot in slots" :key="slot.id">
                          <tr
                            v-for="(line, lineIdx) in getSlotLines(slot)"
                            :key="`${slot.id}-${lineIdx}`"
                            class="border-b border-dashed align-top"
                          >
                            <td
                              v-if="lineIdx === 0"
                              :rowspan="getSlotLines(slot).length"
                              class="py-1 px-1 font-mono border-r border-dashed"
                            >
                              {{ formatTime(slot.start_time) || '—' }}
                            </td>
                            <td
                              v-if="lineIdx === 0"
                              :rowspan="getSlotLines(slot).length"
                              class="py-1 px-1 font-mono border-r border-dashed"
                            >
                              {{ formatTime(slot.end_time) || '—' }}
                            </td>
                            <td
                              v-if="showTitleColumn && lineIdx === 0"
                              :rowspan="getSlotLines(slot).length"
                              class="py-1 px-1 border-r border-dashed"
                            >
                              {{ slot.title }}
                            </td>
                            <td
                              v-if="showLocationColumn && lineIdx === 0"
                              :rowspan="getSlotLines(slot).length"
                              class="py-1 px-1 border-r border-dashed"
                            >
                              {{ slot.location ?? '' }}
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
