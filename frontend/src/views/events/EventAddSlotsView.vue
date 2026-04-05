<script setup lang="ts">
import { computed, onMounted, ref, toRaw, watch } from 'vue'

import type { DateValue } from '@internationalized/date'
import { parseDate } from '@internationalized/date'
import { ArrowLeft, CalendarDays, CalendarPlus, Clock, Plus, X } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useBreadcrumbStore } from '@/stores/breadcrumb'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useFormatters } from '@/composables/useFormatters'
import {
  type RemainderMode,
  type ScheduleConfig,
  useSlotPreview,
} from '@/composables/useSlotPreview'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent } from '@/components/ui/card'
import { CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { DatePicker } from '@/components/ui/date-picker'
import Input from '@/components/ui/input/Input.vue'
import Label from '@/components/ui/label/Label.vue'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'

import ScheduleConfigForm from '@/components/events/ScheduleConfigForm.vue'
import SlotPreviewGrid from '@/components/events/SlotPreviewGrid.vue'

import type { EventGroupRead, EventRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const { t } = useI18n()
const { formatTime, formatDateLabel } = useFormatters()
const route = useRoute()
const router = useRouter()
const breadcrumbStore = useBreadcrumbStore()
const { get, post } = useAuthenticatedClient()

const eventId = computed(() => route.params.eventId as string)
const loading = ref(true)
const submitting = ref(false)
const event = ref<EventRead | null>(null)
const eventGroup = ref<EventGroupRead | null>(null)

// --- Event group date constraints ---
const groupMinDate = computed(() =>
  eventGroup.value ? parseDate(eventGroup.value.start_date) : undefined,
)
const groupMaxDate = computed(() =>
  eventGroup.value ? parseDate(eventGroup.value.end_date) : undefined,
)

// --- Batch-specific fields ---
const location = ref('')
const category = ref('')

// --- Dates ---
const dateMode = ref<'single' | 'range' | 'specific'>('single')
const singleDate = ref<DateValue>()
const rangeStartDate = ref<DateValue>()
const rangeEndDate = ref<DateValue>()
const specificDates = ref<DateValue[]>([])
const specificDatePicker = ref<DateValue>()

const startDate = computed((): DateValue | undefined => {
  if (dateMode.value === 'single') return singleDate.value
  if (dateMode.value === 'range') return rangeStartDate.value
  if (dateMode.value === 'specific' && specificDates.value.length > 0) {
    const raw = specificDates.value.map((d) => toRaw(d) as DateValue)
    let min = raw[0]
    for (const d of raw) {
      if (d.compare(min) < 0) min = d
    }
    return min
  }
  return undefined
})

const endDate = computed((): DateValue | undefined => {
  if (dateMode.value === 'single') return singleDate.value
  if (dateMode.value === 'range') return rangeEndDate.value
  if (dateMode.value === 'specific' && specificDates.value.length > 0) {
    const raw = specificDates.value.map((d) => toRaw(d) as DateValue)
    let max = raw[0]
    for (const d of raw) {
      if (d.compare(max) > 0) max = d
    }
    return max
  }
  return undefined
})

const addSpecificDate = () => {
  if (!specificDatePicker.value) return
  const newDate = toRaw(specificDatePicker.value)
  const already = specificDates.value.some((d) => toRaw(d).compare(newDate) === 0)
  if (!already) {
    specificDates.value.push(newDate)
    specificDates.value.sort((a, b) => (toRaw(a) as DateValue).compare(toRaw(b) as DateValue))
  }
  specificDatePicker.value = undefined
}

const removeSpecificDate = (index: number) => {
  specificDates.value.splice(index, 1)
}

watch(dateMode, () => {
  singleDate.value = undefined
  rangeStartDate.value = undefined
  rangeEndDate.value = undefined
  specificDates.value = []
  specificDatePicker.value = undefined
  overrides.value = []
})

// --- Schedule ---
const defaultStartTime = ref('10:00')
const defaultEndTime = ref('18:00')
const slotDurationMinutes = ref(30)
const peoplePerSlot = ref(2)
const remainderMode = ref<RemainderMode>('drop')
const overrides = ref<Array<{ date: string; startTime: string; endTime: string }>>([])

// --- Slot preview ---
const scheduleConfig = computed<ScheduleConfig>(() => ({
  eventName: event.value?.name || 'Event',
  startDate: startDate.value?.toString() ?? '',
  endDate: endDate.value?.toString() ?? '',
  specificDates:
    dateMode.value === 'specific' ? specificDates.value.map((d) => d.toString()) : undefined,
  defaultStartTime: defaultStartTime.value,
  defaultEndTime: defaultEndTime.value,
  slotDurationMinutes: slotDurationMinutes.value,
  peoplePerSlot: peoplePerSlot.value,
  remainderMode: remainderMode.value,
  overrides: overrides.value,
}))

const {
  totalSlots,
  totalDays,
  slotsByDate,
  hasRemainder,
  excludedSlots,
  toggleSlotExclusion,
  isSlotExcluded,
} = useSlotPreview(scheduleConfig)

watch(rangeStartDate, (val) => {
  if (val && rangeEndDate.value && rangeEndDate.value.compare(val) < 0) {
    rangeEndDate.value = undefined
  }
})

// --- Available dates for exceptions ---
const availableDates = computed(() => {
  if (!startDate.value || !endDate.value) return []

  if (dateMode.value === 'specific') {
    return specificDates.value
      .map((d) => d.toString())
      .filter((dateStr) => !overrides.value.some((o) => o.date === dateStr))
  }

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

// --- Validation ---
const isDatesValid = computed(() => {
  if (dateMode.value === 'single') return !!singleDate.value
  if (dateMode.value === 'range') return !!rangeStartDate.value && !!rangeEndDate.value
  if (dateMode.value === 'specific') return specificDates.value.length > 0
  return false
})

const isValid = computed(() => {
  return (
    isDatesValid.value &&
    !!defaultStartTime.value &&
    !!defaultEndTime.value &&
    slotDurationMinutes.value >= 1 &&
    totalSlots.value > 0
  )
})

// --- Load event ---
const loadEvent = async () => {
  loading.value = true
  try {
    const response = await get<{ data: EventRead }>({
      url: `/events/${eventId.value}`,
    })
    event.value = response.data
    const ev = response.data

    // Fetch event group for date constraints
    if (ev.event_group_id) {
      try {
        const groupResponse = await get<{ data: EventGroupRead }>({
          url: `/event-groups/${ev.event_group_id}`,
        })
        eventGroup.value = groupResponse.data
      } catch {
        // Non-critical — continue without constraints
      }
    }

    // Pre-fill from event defaults
    location.value = ev.location ?? ''
    category.value = ev.category ?? ''
    if (ev.default_start_time) defaultStartTime.value = formatTime(ev.default_start_time)
    if (ev.default_end_time) defaultEndTime.value = formatTime(ev.default_end_time)
    if (ev.slot_duration_minutes) slotDurationMinutes.value = ev.slot_duration_minutes
    if (ev.people_per_slot) peoplePerSlot.value = ev.people_per_slot

    breadcrumbStore.setBreadcrumbs([
      { title: 'Events', titleKey: 'duties.events.title', to: { name: 'events' } },
      { title: ev.name, to: { name: 'event-detail', params: { eventId: ev.id } } },
      { title: t('duties.events.addSlotsView.title') },
    ])
  } catch (error) {
    toastApiError(error)
    router.push({ name: 'events' })
  } finally {
    loading.value = false
  }
}

// --- Submit ---
const handleSubmit = async () => {
  if (!isValid.value || submitting.value) return
  submitting.value = true

  try {
    const response = await post<{ data: { slots_added: number } }>({
      url: `/events/${eventId.value}/add-slots`,
      body: {
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
      },
    })

    toast.success(t('duties.events.addSlotsView.success', { count: response.data.slots_added }))
    router.push({ name: 'event-detail', params: { eventId: eventId.value } })
  } catch (error) {
    toastApiError(error)
  } finally {
    submitting.value = false
  }
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
        <h1 data-testid="page-heading" class="text-3xl font-bold">{{ t('duties.events.addSlotsView.title') }}</h1>
        <p class="text-muted-foreground">
          {{ t('duties.events.addSlotsView.subtitle') }}
          <span class="font-medium text-foreground">{{ event.name }}</span>
        </p>
      </div>

      <!-- Batch Details (location / category) -->
      <Card>
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

      <!-- Dates -->
      <Card>
        <CardHeader>
          <div class="flex items-center gap-3">
            <CalendarDays class="h-5 w-5 text-primary" />
            <div>
              <CardTitle>{{ t('duties.events.createView.sections.dates') }}</CardTitle>
              <CardDescription>{{
                t('duties.events.createView.sections.datesDesc')
              }}</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent class="space-y-4">
          <RadioGroup v-model="dateMode" class="flex gap-4">
            <div class="flex items-center gap-2">
              <RadioGroupItem value="single" id="dm-single" />
              <Label for="dm-single">{{ t('duties.events.createView.dateMode.single') }}</Label>
            </div>
            <div class="flex items-center gap-2">
              <RadioGroupItem value="range" id="dm-range" />
              <Label for="dm-range">{{ t('duties.events.createView.dateMode.range') }}</Label>
            </div>
            <div class="flex items-center gap-2">
              <RadioGroupItem value="specific" id="dm-specific" />
              <Label for="dm-specific">{{ t('duties.events.createView.dateMode.specific') }}</Label>
            </div>
          </RadioGroup>

          <!-- Single date -->
          <div v-if="dateMode === 'single'" class="space-y-2">
            <Label>{{ t('duties.dutySlots.fields.date') }} *</Label>
            <DatePicker v-model="singleDate" :min-value="groupMinDate" :max-value="groupMaxDate" />
          </div>

          <!-- Date range -->
          <div v-if="dateMode === 'range'" class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <Label>{{ t('duties.events.fields.startDate') }} *</Label>
              <DatePicker
                v-model="rangeStartDate"
                :min-value="groupMinDate"
                :max-value="rangeEndDate || groupMaxDate"
              />
            </div>
            <div class="space-y-2">
              <Label>{{ t('duties.events.fields.endDate') }} *</Label>
              <DatePicker
                v-model="rangeEndDate"
                :min-value="rangeStartDate || groupMinDate"
                :max-value="groupMaxDate"
                :highlight="rangeStartDate"
              />
            </div>
          </div>

          <!-- Specific dates -->
          <div v-if="dateMode === 'specific'" class="space-y-3">
            <div class="flex items-end gap-3">
              <div class="flex-1 space-y-2">
                <Label>{{ t('duties.events.createView.addDate') }}</Label>
                <DatePicker
                  v-model="specificDatePicker"
                  :min-value="groupMinDate"
                  :max-value="groupMaxDate"
                />
              </div>
              <Button :disabled="!specificDatePicker" @click="addSpecificDate">
                <Plus class="mr-1.5 h-4 w-4" />
                {{ t('duties.events.createView.addDate') }}
              </Button>
            </div>
            <div
              v-if="specificDates.length === 0"
              class="py-4 text-center text-sm text-muted-foreground"
            >
              {{ t('duties.events.createView.noDatesSelected') }}
            </div>
            <div v-else class="flex flex-wrap gap-2">
              <Badge
                v-for="(date, index) in specificDates"
                :key="date.toString()"
                variant="secondary"
                class="gap-1 py-1.5 pl-3 pr-1.5"
              >
                {{ formatDateLabel(date.toString()) }}
                <button
                  class="ml-1 rounded-full p-0.5 hover:bg-muted"
                  @click="removeSpecificDate(index)"
                >
                  <X class="h-3 w-3" />
                </button>
              </Badge>
            </div>
          </div>
        </CardContent>
      </Card>

      <!-- Schedule -->
      <Card>
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
            :show-overrides="dateMode !== 'single'"
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
          <CalendarPlus class="mr-2 h-4 w-4" />
          {{ submitting ? t('common.states.saving') : t('duties.events.addSlotsView.submit') }}
        </Button>
      </div>
    </template>
  </div>
</template>
