<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import type { DateValue } from '@internationalized/date'
import { parseDate } from '@internationalized/date'
import { ArrowLeft, Clock, Info, RefreshCw } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useBreadcrumbStore } from '@/stores/breadcrumb'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useFormatters } from '@/composables/useFormatters'
import {
  type RemainderMode,
  type ScheduleConfig,
  slotKey,
  useSlotPreview,
} from '@/composables/useSlotPreview'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { DatePicker } from '@/components/ui/date-picker'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import Input from '@/components/ui/input/Input.vue'
import Label from '@/components/ui/label/Label.vue'
import Textarea from '@/components/ui/textarea/Textarea.vue'

import ScheduleConfigForm from '@/components/events/ScheduleConfigForm.vue'
import SlotPreviewGrid from '@/components/events/SlotPreviewGrid.vue'

import type { DutySlotRead, EventRead, SlotBatchRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const { t } = useI18n()
const { formatTime, formatDateLabel } = useFormatters()
const route = useRoute()
const router = useRouter()
const breadcrumbStore = useBreadcrumbStore()
const { get, post, patch } = useAuthenticatedClient()

const eventId = computed(() => route.params.eventId as string)
const batchId = computed(() => (route.query.batchId as string) || null)
const isBatchMode = computed(() => !!batchId.value)
const loading = ref(true)
const submitting = ref(false)
const event = ref<EventRead | null>(null)
const batch = ref<SlotBatchRead | null>(null)

// --- Form state ---
const name = ref('')
const description = ref('')
const location = ref('')
const category = ref('')
const startDate = ref<DateValue>()
const endDate = ref<DateValue>()

// Schedule
const defaultStartTime = ref('10:00')
const defaultEndTime = ref('18:00')
const slotDurationMinutes = ref(30)
const peoplePerSlot = ref(2)
const remainderMode = ref<RemainderMode>('drop')
const overrides = ref<Array<{ date: string; startTime: string; endTime: string }>>([])

// Original schedule snapshot (to detect changes)
interface ScheduleSnapshot {
  startDate: string
  endDate: string
  defaultStartTime: string
  defaultEndTime: string
  slotDurationMinutes: number
  peoplePerSlot: number
  overrides: string // JSON-serialized for easy comparison
}
const originalSchedule = ref<ScheduleSnapshot | null>(null)
const originalExcludedSlots = ref<Set<string>>(new Set())

const currentScheduleSnapshot = computed<ScheduleSnapshot | null>(() => {
  if (!startDate.value || !endDate.value) return null
  return {
    startDate: startDate.value.toString(),
    endDate: endDate.value.toString(),
    defaultStartTime: defaultStartTime.value,
    defaultEndTime: defaultEndTime.value,
    slotDurationMinutes: slotDurationMinutes.value,
    peoplePerSlot: peoplePerSlot.value,
    overrides: JSON.stringify(overrides.value),
  }
})

// Affected bookings dialog
const showAffectedDialog = ref(false)

interface AffectedBooking {
  booking_id: string
  user_id: string
  slot_title: string
  slot_date: string
  slot_start_time: string | null
  slot_end_time: string | null
}

interface RegenerationResult {
  event: EventRead
  slots_added: number
  slots_removed: number
  slots_kept: number
  affected_bookings: AffectedBooking[]
}

const pendingPreview = ref<RegenerationResult | null>(null)

// --- Existing slot bookings (fetched from backend) ---
const existingBookings = ref(new Map<string, number>())

const getSlotBookingCount = (slot: {
  date: string
  startTime: string
  endTime: string
}): number => {
  const key = `${slot.date}|${slot.startTime}|${slot.endTime}`
  return existingBookings.value.get(key) ?? 0
}

// --- Slot preview ---
const scheduleConfig = computed<ScheduleConfig>(() => ({
  eventName: name.value || 'Event',
  startDate: startDate.value?.toString() ?? '',
  endDate: endDate.value?.toString() ?? '',
  defaultStartTime: defaultStartTime.value,
  defaultEndTime: defaultEndTime.value,
  slotDurationMinutes: slotDurationMinutes.value,
  peoplePerSlot: peoplePerSlot.value,
  remainderMode: remainderMode.value,
  overrides: overrides.value,
}))

const {
  previewSlots,
  totalSlots,
  totalDays,
  slotsByDate,
  hasRemainder,
  excludedSlots,
  toggleSlotExclusion,
  isSlotExcluded,
} = useSlotPreview(scheduleConfig)

const excludedSlotsChanged = computed(() => {
  const orig = originalExcludedSlots.value
  const curr = excludedSlots.value
  if (orig.size !== curr.size) return true
  for (const key of orig) {
    if (!curr.has(key)) return true
  }
  return false
})

const scheduleChanged = computed(() => {
  if (excludedSlotsChanged.value) return true
  if (!originalSchedule.value || !currentScheduleSnapshot.value) return true
  const orig = originalSchedule.value
  const curr = currentScheduleSnapshot.value
  return (
    orig.startDate !== curr.startDate ||
    orig.endDate !== curr.endDate ||
    orig.defaultStartTime !== curr.defaultStartTime ||
    orig.defaultEndTime !== curr.defaultEndTime ||
    orig.slotDurationMinutes !== curr.slotDurationMinutes ||
    orig.peoplePerSlot !== curr.peoplePerSlot ||
    orig.overrides !== curr.overrides
  )
})

const isValid = computed(() => {
  const hasName = isBatchMode.value || !!name.value.trim()
  return (
    hasName &&
    !!startDate.value &&
    !!endDate.value &&
    !!defaultStartTime.value &&
    !!defaultEndTime.value &&
    slotDurationMinutes.value >= 1 &&
    totalSlots.value > 0
  )
})

// --- Date sync ---
watch(startDate, (val) => {
  if (val && endDate.value && endDate.value.compare(val) < 0) {
    endDate.value = undefined
  }
})

// --- Available dates for exceptions ---
const availableDates = computed(() => {
  if (!startDate.value || !endDate.value) return []
  const dates: string[] = []
  const start = new Date(startDate.value.toString())
  const end = new Date(endDate.value.toString())
  const current = new Date(start)
  while (current <= end) {
    const dateStr = current.toISOString().split('T')[0]
    if (!overrides.value.some((o) => o.date === dateStr)) {
      dates.push(dateStr)
    }
    current.setDate(current.getDate() + 1)
  }
  return dates
})

// --- Load event data ---
const loadEvent = async () => {
  loading.value = true
  try {
    const response = await get<{ data: EventRead }>({
      url: `/events/${eventId.value}`,
    })
    event.value = response.data
    const ev = response.data

    // Populate form — use batch config if in batch mode
    name.value = ev.name
    description.value = ev.description ?? ''

    if (batchId.value) {
      // Load batch and use its config
      try {
        const batchRes = await get<{ data: SlotBatchRead[] }>({
          url: `/events/${eventId.value}/batches`,
        })
        batch.value = batchRes.data.find((b: SlotBatchRead) => b.id === batchId.value) ?? null
      } catch {
        // Fall through to event-level config
      }
    }

    const src = batch.value
    if (src) {
      location.value = src.location ?? ''
      category.value = src.category ?? ''
      startDate.value = parseDate(src.start_date)
      endDate.value = parseDate(src.end_date)
      if (src.default_start_time) defaultStartTime.value = formatTime(src.default_start_time)
      if (src.default_end_time) defaultEndTime.value = formatTime(src.default_end_time)
      if (src.slot_duration_minutes) slotDurationMinutes.value = src.slot_duration_minutes
      if (src.people_per_slot) peoplePerSlot.value = src.people_per_slot
      if (src.remainder_mode) remainderMode.value = src.remainder_mode as RemainderMode
      if (src.schedule_overrides) {
        overrides.value = (
          src.schedule_overrides as Array<{ date: string; start_time: string; end_time: string }>
        ).map((o) => ({
          date: o.date,
          startTime: formatTime(o.start_time),
          endTime: formatTime(o.end_time),
        }))
      }
    } else {
      location.value = ev.location ?? ''
      category.value = ev.category ?? ''
      startDate.value = parseDate(ev.start_date)
      endDate.value = parseDate(ev.end_date)
      if (ev.default_start_time) defaultStartTime.value = formatTime(ev.default_start_time)
      if (ev.default_end_time) defaultEndTime.value = formatTime(ev.default_end_time)
      if (ev.slot_duration_minutes) slotDurationMinutes.value = ev.slot_duration_minutes
      if (ev.people_per_slot) peoplePerSlot.value = ev.people_per_slot
      if (ev.schedule_overrides) {
        overrides.value = (
          ev.schedule_overrides as Array<{ date: string; start_time: string; end_time: string }>
        ).map((o) => ({
          date: o.date,
          startTime: formatTime(o.start_time),
          endTime: formatTime(o.end_time),
        }))
      }
    }

    // Snapshot original schedule for change detection
    originalSchedule.value = {
      startDate: startDate.value!.toString(),
      endDate: endDate.value!.toString(),
      defaultStartTime: defaultStartTime.value,
      defaultEndTime: defaultEndTime.value,
      slotDurationMinutes: slotDurationMinutes.value,
      peoplePerSlot: peoplePerSlot.value,
      overrides: JSON.stringify(overrides.value),
    }

    // Fetch existing slots with booking counts (scoped to batch if applicable)
    try {
      const slotsRes = await get<{ data: { items: DutySlotRead[] } }>({
        url: '/duty-slots/',
        query: { event_id: eventId.value, limit: 200 },
      })
      // Filter to batch slots only when in batch mode
      const relevantSlots = batchId.value
        ? slotsRes.data.items.filter((s: DutySlotRead) => s.batch_id === batchId.value)
        : slotsRes.data.items
      const bookingMap = new Map<string, number>()
      const existingKeys = new Set<string>()
      for (const slot of relevantSlots) {
        const st = formatTime(slot.start_time)
        const et = formatTime(slot.end_time)
        const key = `${slot.date}|${st}|${et}`
        existingKeys.add(key)
        if ((slot.current_bookings ?? 0) > 0) {
          bookingMap.set(key, slot.current_bookings!)
        }
      }
      existingBookings.value = bookingMap

      // Pre-exclude preview slots that were manually deleted from the backend
      const toExclude = new Set<string>()
      for (const previewSlot of previewSlots.value) {
        const key = slotKey(previewSlot)
        if (!existingKeys.has(key)) {
          toExclude.add(key)
        }
      }
      if (toExclude.size > 0) {
        excludedSlots.value = new Set(toExclude)
      }
      // Snapshot the initial excluded state for change detection
      originalExcludedSlots.value = new Set(excludedSlots.value)
    } catch {
      // Non-critical — preview just won't show booking counts
    }

    // Set breadcrumbs
    breadcrumbStore.setBreadcrumbs([
      { title: 'Events', titleKey: 'duties.events.title', to: { name: 'events' } },
      { title: ev.name, to: { name: 'event-detail', params: { eventId: ev.id } } },
      {
        title: isBatchMode.value
          ? t('duties.events.editView.editBatch')
          : t('duties.events.editView.title'),
      },
    ])
  } catch (error) {
    toastApiError(error)
    router.push({ name: 'events' })
  } finally {
    loading.value = false
  }
}

// --- Build request body ---
const buildPayload = () => {
  return {
    name: name.value,
    description: description.value || null,
    start_date: startDate.value!.toString(),
    end_date: endDate.value!.toString(),
    location: location.value || null,
    category: category.value || null,
    schedule: {
      default_start_time: defaultStartTime.value + ':00',
      default_end_time: defaultEndTime.value + ':00',
      slot_duration_minutes: slotDurationMinutes.value,
      people_per_slot: peoplePerSlot.value,
      remainder_mode: remainderMode.value,
      overrides: overrides.value
        .filter((o) => o.date)
        .map((o) => ({
          date: o.date,
          start_time: o.startTime + ':00',
          end_time: o.endTime + ':00',
        })),
      excluded_slots: [...excludedSlots.value].map((key) => {
        const [date, start_time, end_time] = key.split('|')
        return { date, start_time: start_time + ':00', end_time: end_time + ':00' }
      }),
    },
  }
}

// --- Submit ---
const handleSubmit = async () => {
  if (!isValid.value || submitting.value) return
  submitting.value = true

  try {
    if (!scheduleChanged.value && !isBatchMode.value) {
      // Only details changed — simple PATCH, no slot regeneration
      await patch<{ data: EventRead }>({
        url: `/events/${eventId.value}`,
        body: {
          name: name.value,
          description: description.value || null,
          location: location.value || null,
          category: category.value || null,
        },
      })
      toast.success(t('duties.events.editView.saveSuccess'))
      router.push({ name: 'event-detail', params: { eventId: eventId.value } })
      return
    }

    // Schedule changed — dry run first to check for affected bookings
    const regenQuery: Record<string, unknown> = { dry_run: true }
    if (batchId.value) regenQuery.batch_id = batchId.value

    const preview = await post<{ data: RegenerationResult }>({
      url: `/events/${eventId.value}/regenerate-slots`,
      query: regenQuery,
      body: buildPayload(),
    })

    if (preview.data.affected_bookings.length > 0) {
      // Show confirmation dialog
      pendingPreview.value = preview.data
      showAffectedDialog.value = true
      submitting.value = false
      return
    }

    // No affected bookings — proceed directly
    await executeRegeneration()
  } catch (error) {
    toastApiError(error)
    submitting.value = false
  }
}

const executeRegeneration = async () => {
  submitting.value = true
  try {
    const regenQuery: Record<string, unknown> = {}
    if (batchId.value) regenQuery.batch_id = batchId.value

    await post<{ data: RegenerationResult }>({
      url: `/events/${eventId.value}/regenerate-slots`,
      query: regenQuery,
      body: buildPayload(),
    })

    toast.success(t('duties.events.editView.saveSuccess'))
    router.push({ name: 'event-detail', params: { eventId: eventId.value } })
  } catch (error) {
    toastApiError(error)
  } finally {
    submitting.value = false
  }
}

const confirmRegeneration = async () => {
  showAffectedDialog.value = false
  pendingPreview.value = null
  await executeRegeneration()
}

onMounted(loadEvent)
</script>

<template>
  <div class="mx-auto max-w-3xl space-y-6">
    <!-- Loading -->
    <div v-if="loading" class="text-center py-12 text-muted-foreground">
      {{ t('common.states.loading') }}
    </div>

    <template v-else-if="event">
      <!-- Header -->
      <div class="space-y-2">
        <Button
          data-testid="btn-back"
          variant="ghost"
          size="sm"
          class="-ml-2"
          @click="router.push({ name: 'event-detail', params: { eventId: eventId } })"
        >
          <ArrowLeft class="mr-1.5 h-4 w-4" />
          {{ t('common.actions.back') }}
        </Button>
        <h1 data-testid="page-heading" class="text-3xl font-bold">
          {{
            isBatchMode ? t('duties.events.editView.editBatch') : t('duties.events.editView.title')
          }}
        </h1>
        <p class="text-muted-foreground">
          {{
            isBatchMode
              ? t('duties.events.editView.editBatchSubtitle')
              : t('duties.events.editView.subtitle')
          }}
        </p>
      </div>

      <!-- Event Details (hidden in batch mode) -->
      <Card v-if="!isBatchMode">
        <CardHeader>
          <CardTitle>{{ t('duties.events.createView.sections.details') }}</CardTitle>
          <CardDescription>{{
            t('duties.events.createView.sections.detailsDesc')
          }}</CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="space-y-2">
            <Label>{{ t('duties.events.fields.name') }} *</Label>
            <Input v-model="name" />
          </div>
          <div class="space-y-2">
            <Label>{{ t('duties.events.fields.description') }}</Label>
            <Textarea v-model="description" :rows="3" class="max-h-[150px]" />
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <Label>{{ t('duties.events.fields.location') }}</Label>
              <Input v-model="location" />
            </div>
            <div class="space-y-2">
              <Label>{{ t('duties.events.fields.category') }}</Label>
              <Input v-model="category" />
            </div>
          </div>
        </CardContent>
      </Card>

      <!-- Batch Details (only in batch mode) -->
      <Card v-if="isBatchMode">
        <CardHeader>
          <CardTitle>{{ t('duties.events.addSlotsView.sections.batch') }}</CardTitle>
          <CardDescription>{{
            t('duties.events.addSlotsView.sections.batchDesc')
          }}</CardDescription>
        </CardHeader>
        <CardContent>
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <Label>{{ t('duties.events.fields.location') }}</Label>
              <Input v-model="location" />
            </div>
            <div class="space-y-2">
              <Label>{{ t('duties.events.fields.category') }}</Label>
              <Input v-model="category" />
            </div>
          </div>
        </CardContent>
      </Card>

      <!-- Event Dates -->
      <Card>
        <CardHeader>
          <CardTitle>{{ t('duties.events.createView.sections.dates') }}</CardTitle>
          <CardDescription>{{ t('duties.events.createView.sections.datesDesc') }}</CardDescription>
        </CardHeader>
        <CardContent>
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <Label>{{ t('duties.events.fields.startDate') }} *</Label>
              <DatePicker v-model="startDate" :max-value="endDate" />
            </div>
            <div class="space-y-2">
              <Label>{{ t('duties.events.fields.endDate') }} *</Label>
              <DatePicker v-model="endDate" :min-value="startDate" :highlight="startDate" />
            </div>
          </div>
        </CardContent>
      </Card>

      <!-- Schedule & Slots -->
      <Card data-testid="section-schedule">
        <CardHeader>
          <div class="flex items-center gap-3">
            <Clock class="h-5 w-5 text-primary" />
            <div>
              <CardTitle>{{ t('duties.events.createView.sections.schedule') }}</CardTitle>
              <CardDescription>{{
                t('duties.events.createView.sections.scheduleDesc')
              }}</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent class="space-y-6">
          <ScheduleConfigForm
            v-model:default-start-time="defaultStartTime"
            v-model:default-end-time="defaultEndTime"
            v-model:slot-duration-minutes="slotDurationMinutes"
            v-model:people-per-slot="peoplePerSlot"
            v-model:remainder-mode="remainderMode"
            v-model:overrides="overrides"
            :has-remainder="hasRemainder"
            :available-dates="availableDates"
            show-overrides
          />
        </CardContent>
      </Card>

      <!-- Preview -->
      <Card>
        <CardHeader>
          <div class="flex items-center justify-between">
            <div>
              <CardTitle>{{ t('duties.events.createView.sections.preview') }}</CardTitle>
              <CardDescription>{{
                t('duties.events.createView.sections.previewDesc')
              }}</CardDescription>
            </div>
            <Badge v-if="totalSlots > 0" variant="secondary">
              {{
                t('duties.events.createView.preview.summary', {
                  slots: totalSlots,
                  days: totalDays,
                })
              }}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div v-if="totalSlots === 0" class="py-8 text-center text-muted-foreground">
            {{ t('duties.events.createView.preview.noSlots') }}
          </div>
          <div v-else>
            <SlotPreviewGrid
              :slots-by-date="slotsByDate"
              :is-slot-excluded="isSlotExcluded"
              :get-booking-count="getSlotBookingCount"
              @toggle-exclusion="toggleSlotExclusion"
            />
          </div>
        </CardContent>
      </Card>

      <!-- Actions -->
      <div class="flex justify-end gap-3">
        <Button
          data-testid="btn-cancel"
          variant="outline"
          @click="router.push({ name: 'event-detail', params: { eventId: eventId } })"
        >
          {{ t('common.actions.cancel') }}
        </Button>
        <Button data-testid="btn-submit" :disabled="!isValid || submitting" @click="handleSubmit">
          <RefreshCw v-if="scheduleChanged" class="mr-2 h-4 w-4" />
          {{
            submitting
              ? t('duties.events.editView.saving')
              : scheduleChanged
                ? t('duties.events.editView.regenerate')
                : t('common.actions.save')
          }}
        </Button>
      </div>
    </template>

    <!-- Affected Bookings Dialog -->
    <Dialog v-model:open="showAffectedDialog">
      <DialogContent class="max-w-lg">
        <DialogHeader>
          <DialogTitle class="flex items-center gap-2">
            <Info class="h-5 w-5 text-destructive" />
            {{ t('duties.events.editView.affectedBookings.title') }}
          </DialogTitle>
          <DialogDescription>
            {{ t('duties.events.editView.affectedBookings.description') }}
          </DialogDescription>
        </DialogHeader>

        <div v-if="pendingPreview" class="space-y-3">
          <!-- Summary badges -->
          <div class="flex gap-2 flex-wrap">
            <Badge variant="default">
              {{ t('duties.events.editView.preview.added', { count: pendingPreview.slots_added }) }}
            </Badge>
            <Badge variant="destructive">
              {{
                t('duties.events.editView.preview.removed', { count: pendingPreview.slots_removed })
              }}
            </Badge>
            <Badge variant="secondary">
              {{ t('duties.events.editView.preview.kept', { count: pendingPreview.slots_kept }) }}
            </Badge>
          </div>

          <!-- Affected bookings list -->
          <div class="max-h-60 space-y-2 overflow-y-auto rounded-md border p-3">
            <div
              v-for="booking in pendingPreview.affected_bookings"
              :key="booking.booking_id"
              class="flex items-center justify-between rounded-md bg-muted/50 px-3 py-2 text-sm"
            >
              <div>
                <p class="font-medium">{{ booking.slot_title }}</p>
                <p class="text-muted-foreground">
                  {{ formatDateLabel(booking.slot_date) }}
                  <template v-if="booking.slot_start_time">
                    {{ formatTime(booking.slot_start_time) }} -
                    {{ formatTime(booking.slot_end_time) }}
                  </template>
                </p>
              </div>
              <Badge variant="outline" class="text-xs">
                {{ booking.user_id.substring(0, 8) }}...
              </Badge>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" @click="showAffectedDialog = false">
            {{ t('duties.events.editView.affectedBookings.cancel') }}
          </Button>
          <Button variant="destructive" @click="confirmRegeneration">
            {{ t('duties.events.editView.affectedBookings.confirm') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
