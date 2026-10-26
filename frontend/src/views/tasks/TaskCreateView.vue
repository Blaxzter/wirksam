<script setup lang="ts">
import { computed, nextTick, onMounted, ref, toRaw, watch } from 'vue'

import type { DateValue } from '@internationalized/date'
import { getLocalTimeZone, parseDate, today } from '@internationalized/date'
import { ArrowLeft, CalendarDays, CalendarPlus, Clock, Plus, Users, X } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useFormatters } from '@/composables/useFormatters'
import {
  type RemainderMode,
  type ScheduleConfig,
  eachDateInRange,
  useShiftPreview,
} from '@/composables/useShiftPreview'

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { DatePicker } from '@/components/ui/date-picker'
import Input from '@/components/ui/input/Input.vue'
import Label from '@/components/ui/label/Label.vue'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import Textarea from '@/components/ui/textarea/Textarea.vue'

import TeamPicker from '@/components/events/teams/TeamPicker.vue'
import LocationPicker from '@/components/locations/LocationPicker.vue'
import ScheduleConfigForm from '@/components/tasks/ScheduleConfigForm.vue'
import ShiftPreviewGrid from '@/components/tasks/ShiftPreviewGrid.vue'

import type { EventListResponse, EventRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const { t } = useI18n()
const { formatDateLabel } = useFormatters()
const route = useRoute()
const router = useRouter()
const { get, post } = useAuthenticatedClient()
const authStore = useAuthStore()

// Prefill task event from query param (e.g. when creating from EventDetailView)
const prefillGroupId = route.query.eventId as string | undefined

// --- Form state ---
const name = ref('')
const description = ref('')
const location = ref('')
const locationId = ref<string | null>(null)
const category = ref('')
const teamId = ref<string | null>(null)

// Task event
const isScopedManagerOnly = computed(() => !authStore.isAdmin && authStore.isEventManager)
const eventMode = ref<'none' | 'existing' | 'new'>(isScopedManagerOnly.value ? 'existing' : 'none')
const selectedEventId = ref<string>('')
const events = ref<EventRead[]>([])
const newEventName = ref('')
const newEventDescription = ref('')
const newEventStartDate = ref<DateValue>()
const newEventEndDate = ref<DateValue>()

// Dates
const dateMode = ref<'single' | 'range' | 'specific'>('single')
const singleDate = ref<DateValue>()
const rangeStartDate = ref<DateValue>()
const rangeEndDate = ref<DateValue>()
const specificDates = ref<DateValue[]>([])
const specificDatePicker = ref<DateValue>()

// Computed effective start/end dates (derived from date mode)
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

// Date constraints from task event
const selectedEvent = computed(() => {
  if (eventMode.value === 'existing' && selectedEventId.value) {
    return events.value.find((g) => g.id === selectedEventId.value)
  }
  return null
})

const eventMinDate = computed(() => {
  if (selectedEvent.value) return parseDate(selectedEvent.value.start_date)
  if (eventMode.value === 'new' && newEventStartDate.value) return newEventStartDate.value
  return undefined
})

const eventMaxDate = computed(() => {
  if (selectedEvent.value) return parseDate(selectedEvent.value.end_date)
  if (eventMode.value === 'new' && newEventEndDate.value) return newEventEndDate.value
  return undefined
})

const hasEventDateConstraint = computed(() => !!eventMinDate.value && !!eventMaxDate.value)

// Add specific date
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

// Clear dates when mode changes
watch(dateMode, () => {
  singleDate.value = undefined
  rangeStartDate.value = undefined
  rangeEndDate.value = undefined
  specificDates.value = []
  specificDatePicker.value = undefined
  overrides.value = []
})

// Locations belong to one event, so the picker only offers them once an
// existing event is chosen.
const locationEventId = computed(() =>
  eventMode.value === 'existing' && selectedEventId.value ? selectedEventId.value : null,
)
// A location of the previous event would be refused; keep its name as text.
watch(locationEventId, () => {
  locationId.value = null
  // Teams belong to one event too, and have no text to fall back on.
  teamId.value = null
})

// Clear dates when event changes (constraints may have changed)
watch([eventMode, selectedEventId], () => {
  singleDate.value = undefined
  rangeStartDate.value = undefined
  rangeEndDate.value = undefined
  specificDates.value = []
})

// Schedule
const defaultStartTime = ref('10:00')
const defaultEndTime = ref('18:00')
const shiftDurationMinutes = ref(30)
const peoplePerShift = ref(2)
const remainderMode = ref<RemainderMode>('drop')
const overrides = ref<Array<{ date: string; startTime: string; endTime: string }>>([])

// UI state
const submitting = ref(false)
const activeSection = ref('details')

const sections = ['details', 'event', 'dates', 'schedule', 'preview'] as const

const isDetailsValid = computed(() => {
  return !!name.value.trim()
})

const isEventValid = computed(() => {
  if (eventMode.value === 'existing') return !!selectedEventId.value
  if (eventMode.value === 'new') {
    return !!newEventName.value.trim() && !!newEventStartDate.value && !!newEventEndDate.value
  }
  return true
})

const isDatesValid = computed(() => {
  if (dateMode.value === 'single') return !!singleDate.value
  if (dateMode.value === 'range') return !!rangeStartDate.value && !!rangeEndDate.value
  if (dateMode.value === 'specific') return specificDates.value.length > 0
  return false
})

const isScheduleValid = computed(() => {
  return !!defaultStartTime.value && !!defaultEndTime.value && shiftDurationMinutes.value >= 1
})

const sectionValid: Record<string, () => boolean> = {
  details: () => isDetailsValid.value,
  event: () => isEventValid.value,
  dates: () => isDatesValid.value,
  schedule: () => isScheduleValid.value,
}

const isCurrentSectionValid = computed(() => {
  const check = sectionValid[activeSection.value]
  return check ? check() : true
})

const goToNext = () => {
  const idx = sections.indexOf(activeSection.value as (typeof sections)[number])
  if (idx < sections.length - 1) {
    activeSection.value = sections[idx + 1]
  }
}

// --- Shift preview ---
const scheduleConfig = computed<ScheduleConfig>(() => ({
  eventName: name.value || 'Task',
  startDate: startDate.value?.toString() ?? '',
  endDate: endDate.value?.toString() ?? '',
  specificDates:
    dateMode.value === 'specific' ? specificDates.value.map((d) => d.toString()) : undefined,
  defaultStartTime: defaultStartTime.value,
  defaultEndTime: defaultEndTime.value,
  shiftDurationMinutes: shiftDurationMinutes.value,
  peoplePerShift: peoplePerShift.value,
  remainderMode: remainderMode.value,
  overrides: overrides.value,
}))

const {
  totalShifts,
  totalDays,
  shiftsByDate,
  hasRemainder,
  excludedShifts,
  toggleShiftExclusion,
  isShiftExcluded,
} = useShiftPreview(scheduleConfig)

// --- Date sync ---
watch(rangeStartDate, (val) => {
  if (val && rangeEndDate.value && rangeEndDate.value.compare(val) < 0) {
    rangeEndDate.value = undefined
  }
})

// --- Load task events ---
const loadEvents = async () => {
  try {
    const response = await get<{ data: EventListResponse }>({
      url: '/events/',
      query: { limit: 100 },
    })
    let items = response.data.items

    // Scoped event managers can only create tasks in their managed events
    const managedIds = authStore.managedEventIds
    if (!authStore.isAdmin && managedIds.length > 0) {
      items = items.filter((g) => managedIds.includes(g.id))
    }

    events.value = items

    // Prefill task event selection if eventId query param is present
    if (prefillGroupId && events.value.some((g) => g.id === prefillGroupId)) {
      eventMode.value = 'existing'
      selectedEventId.value = prefillGroupId
    }
  } catch {
    // Non-critical, just won't have events to select from
  }
}

/**
 * Fill the form with a worked example, for the guided tour only.
 *
 * Verified necessary: `name` starts `''` and `singleDate` `undefined`, so
 * `totalShifts` is 0 and the preview section renders its `preview.noShifts`
 * empty state — the manager tour's most persuasive screen would otherwise
 * describe an empty box.
 *
 * The reka-ui DatePicker is never driven by clicking; the values are written
 * straight into the refs.
 *
 * The two `nextTick`s are load-bearing: `watch([eventMode, selectedEventId])`
 * and `watch(dateMode)` both clear every date ref, and they flush *after* the
 * assignment that triggered them. Writing the dates in the same tick means
 * watching them be wiped a moment later.
 */
const applyTourPrefill = async () => {
  if (route.query.tour !== 'prefill') return
  // The one gate that matters: a real organiser must never find their form
  // filled in behind their back, whatever ends up in the query string.
  if (!authStore.profile?.is_sandbox) return
  const untouched =
    !name.value.trim() &&
    !singleDate.value &&
    !rangeStartDate.value &&
    !rangeEndDate.value &&
    specificDates.value.length === 0
  if (!untouched) return

  const eventId = authStore.selectedEventId
  const event = eventId ? events.value.find((e) => e.id === eventId) : undefined
  if (!event) return

  eventMode.value = 'existing'
  selectedEventId.value = event.id
  await nextTick()

  dateMode.value = 'range'
  await nextTick()

  const min = parseDate(event.start_date)
  const max = parseDate(event.end_date)
  const from = today(getLocalTimeZone())
  const start = from.compare(min) < 0 ? min : from
  const threeDays = start.add({ days: 2 })
  rangeStartDate.value = start
  rangeEndDate.value = threeDays.compare(max) > 0 ? max : threeDays

  name.value = t('duties.tasks.createView.tourExample.name')
  location.value = t('duties.tasks.createView.tourExample.location')
  description.value = t('duties.tasks.createView.tourExample.description')
  // 10:00–18:00 in two-hour blocks over three days = 12 shifts: enough for the
  // preview to be convincing, few enough to read, and the same block length the
  // seeded tasks use, so the example looks native.
  shiftDurationMinutes.value = 120
  peoplePerShift.value = 2
}

onMounted(async () => {
  await loadEvents()
  await applyTourPrefill()
})

// --- Available dates for exceptions ---
const availableDates = computed(() => {
  if (!startDate.value || !endDate.value) return []

  if (dateMode.value === 'specific') {
    return specificDates.value
      .map((d) => d.toString())
      .filter((dateStr) => !overrides.value.some((o) => o.date === dateStr))
  }

  return eachDateInRange(startDate.value.toString(), endDate.value.toString()).filter(
    (dateStr) => !overrides.value.some((o) => o.date === dateStr),
  )
})

// --- Form validation ---
const isValid = computed(() => {
  return (
    isDetailsValid.value &&
    isEventValid.value &&
    isDatesValid.value &&
    isScheduleValid.value &&
    totalShifts.value > 0
  )
})

// --- Submit ---
const handleSubmit = async () => {
  if (!isValid.value || submitting.value) return
  submitting.value = true

  try {
    const body: Record<string, unknown> = {
      name: name.value,
      description: description.value || null,
      start_date: startDate.value!.toString(),
      end_date: endDate.value!.toString(),
      location_id: locationEventId.value ? locationId.value : null,
      location: location.value || null,
      category: category.value || null,
      team_id: locationEventId.value ? teamId.value : null,
      schedule: {
        default_start_time: defaultStartTime.value + ':00',
        default_end_time: defaultEndTime.value + ':00',
        shift_duration_minutes: shiftDurationMinutes.value,
        people_per_shift: peoplePerShift.value,
        remainder_mode: remainderMode.value,
        overrides: overrides.value
          .filter((o) => o.date)
          .map((o) => ({
            date: o.date,
            start_time: o.startTime + ':00',
            end_time: o.endTime + ':00',
          })),
        excluded_shifts: Array.from(excludedShifts.value).map((key) => {
          const [date, start_time, end_time] = key.split('|')
          return { date, start_time: start_time + ':00', end_time: end_time + ':00' }
        }),
        // Without this the backend walks every day between start_date and
        // end_date, so the gap days between hand-picked dates get shifts the
        // preview never showed (#144).
        specific_dates:
          dateMode.value === 'specific' ? specificDates.value.map((d) => d.toString()) : null,
      },
    }

    if (eventMode.value === 'existing' && selectedEventId.value) {
      body.event_id = selectedEventId.value
    } else if (eventMode.value === 'new') {
      body.new_event = {
        name: newEventName.value,
        description: newEventDescription.value || null,
        start_date: newEventStartDate.value!.toString(),
        end_date: newEventEndDate.value!.toString(),
      }
    }

    const response = await post<{ data: { task: { id: string }; shifts_created: number } }>({
      url: '/tasks/with-shifts',
      body,
    })

    toast.success(t('duties.tasks.createView.success', { count: response.data.shifts_created }))
    router.push({ name: 'task-detail', params: { eventId: response.data.task.id } })
  } catch (error) {
    toastApiError(error)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-3xl space-y-6">
    <!-- Header -->
    <div class="space-y-2">
      <Button
        data-testid="btn-back"
        variant="ghost"
        size="sm"
        class="-ml-2 max-xl:hidden"
        @click="router.push({ name: 'tasks' })"
      >
        <ArrowLeft class="mr-1.5 h-4 w-4" />
        {{ t('common.actions.back') }}
      </Button>
      <h1 data-testid="page-heading" class="text-2xl sm:text-3xl font-bold">
        {{ t('duties.tasks.createView.title') }}
      </h1>
      <p class="text-muted-foreground">{{ t('duties.tasks.createView.subtitle') }}</p>
    </div>

    <Accordion v-model="activeSection" type="single" collapsible class="space-y-4">
      <!-- Section 1: Task Details -->
      <AccordionItem value="details" data-testid="section-task-details" class="rounded-lg border">
        <AccordionTrigger class="px-6 hover:no-underline">
          <div class="flex items-center gap-3">
            <CalendarPlus class="h-5 w-5 text-primary" />
            <div class="text-left">
              <p class="font-semibold">{{ t('duties.tasks.createView.sections.details') }}</p>
              <p class="text-sm text-muted-foreground">
                {{ t('duties.tasks.createView.sections.detailsDesc') }}
              </p>
            </div>
          </div>
        </AccordionTrigger>
        <AccordionContent class="px-6 pb-6">
          <div class="space-y-4">
            <div class="space-y-2">
              <Label for="task-name">{{ t('duties.tasks.fields.name') }} *</Label>
              <Input id="task-name" v-model="name" data-testid="input-task-name" />
            </div>
            <div class="space-y-2">
              <Label for="task-description">{{ t('duties.tasks.fields.description') }}</Label>
              <Textarea id="task-description" v-model="description" :rows="3" />
            </div>
            <div class="grid items-start gap-4 sm:grid-cols-2">
              <div class="space-y-2">
                <Label for="task-location">{{ t('duties.tasks.fields.location') }}</Label>
                <LocationPicker
                  v-model:location-id="locationId"
                  v-model:text="location"
                  :event-id="locationEventId"
                  :hide-no-event-hint="eventMode === 'new'"
                  input-id="task-location"
                />
              </div>
              <div class="space-y-2">
                <Label for="task-category">{{ t('duties.tasks.fields.category') }}</Label>
                <Input id="task-category" v-model="category" />
              </div>
            </div>
            <!-- Who can book: only an existing event has teams to choose from -->
            <section
              v-if="locationEventId"
              class="space-y-3 border-t pt-4"
              data-testid="section-who-can-book"
              aria-labelledby="who-can-book-heading"
            >
              <div class="space-y-0.5">
                <h3 id="who-can-book-heading" class="font-semibold">
                  {{ t('teamLocks.picker.title') }}
                </h3>
                <p class="text-sm text-muted-foreground">{{ t('teamLocks.picker.subtitle') }}</p>
              </div>
              <TeamPicker v-model="teamId" :event-id="locationEventId" input-id="task-team" />
            </section>
            <div class="flex justify-end pt-2">
              <Button :disabled="!isCurrentSectionValid" @click="goToNext">{{
                t('common.actions.next')
              }}</Button>
            </div>
          </div>
        </AccordionContent>
      </AccordionItem>

      <!-- Section 2: Event -->
      <AccordionItem value="event" data-testid="section-event" class="rounded-lg border">
        <AccordionTrigger class="px-6 hover:no-underline">
          <div class="flex items-center gap-3">
            <Users class="h-5 w-5 text-primary" />
            <div class="text-left">
              <p class="font-semibold">{{ t('duties.tasks.createView.sections.event') }}</p>
              <p class="text-sm text-muted-foreground">
                {{ t('duties.tasks.createView.sections.eventDesc') }}
              </p>
            </div>
          </div>
        </AccordionTrigger>
        <AccordionContent class="px-6 pb-6">
          <RadioGroup v-model="eventMode" class="space-y-3">
            <div v-if="!isScopedManagerOnly" class="flex items-center gap-2">
              <RadioGroupItem value="none" id="eg-none" />
              <Label for="eg-none">{{ t('duties.tasks.createView.eventOption.none') }}</Label>
            </div>
            <div class="flex items-center gap-2">
              <RadioGroupItem value="existing" id="eg-existing" />
              <Label for="eg-existing">{{
                t('duties.tasks.createView.eventOption.existing')
              }}</Label>
            </div>
            <div v-if="!isScopedManagerOnly" class="flex items-center gap-2">
              <RadioGroupItem value="new" id="eg-new" />
              <Label for="eg-new">{{ t('duties.tasks.createView.eventOption.new') }}</Label>
            </div>
          </RadioGroup>

          <!-- Select existing event -->
          <div v-if="eventMode === 'existing'" class="mt-4">
            <Select v-model="selectedEventId">
              <SelectTrigger>
                <SelectValue :placeholder="t('duties.tasks.createView.eventOption.existing')" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="event in events" :key="event.id" :value="event.id">
                  {{ event.name }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <!-- Create new event -->
          <div v-if="eventMode === 'new'" class="mt-4 space-y-4 rounded-md border bg-card p-4">
            <div class="space-y-2">
              <Label for="new-event-name">{{ t('duties.events.fields.name') }} *</Label>
              <Input id="new-event-name" v-model="newEventName" />
            </div>
            <div class="space-y-2">
              <Label for="new-event-description">{{ t('duties.events.fields.description') }}</Label>
              <Input id="new-event-description" v-model="newEventDescription" />
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div class="space-y-2">
                <Label>{{ t('duties.events.fields.startDate') }} *</Label>
                <DatePicker v-model="newEventStartDate" :max-value="newEventEndDate" />
              </div>
              <div class="space-y-2">
                <Label>{{ t('duties.events.fields.endDate') }} *</Label>
                <DatePicker
                  v-model="newEventEndDate"
                  :min-value="newEventStartDate"
                  :highlight="newEventStartDate"
                />
              </div>
            </div>
          </div>
          <div class="mt-4 flex justify-end">
            <Button :disabled="!isCurrentSectionValid" @click="goToNext">{{
              t('common.actions.next')
            }}</Button>
          </div>
        </AccordionContent>
      </AccordionItem>

      <!-- Section 3: Task Dates -->
      <AccordionItem value="dates" data-testid="section-task-dates" class="rounded-lg border">
        <AccordionTrigger class="px-6 hover:no-underline">
          <div class="flex items-center gap-3">
            <CalendarDays class="h-5 w-5 text-primary" />
            <div class="text-left">
              <p class="font-semibold">{{ t('duties.tasks.createView.sections.dates') }}</p>
              <p class="text-sm text-muted-foreground">
                {{ t('duties.tasks.createView.sections.datesDesc') }}
              </p>
            </div>
          </div>
        </AccordionTrigger>
        <AccordionContent class="px-6 pb-6">
          <div class="space-y-4">
            <!-- Event date constraint hint -->
            <p v-if="hasEventDateConstraint" class="text-sm text-muted-foreground">
              {{
                t('duties.tasks.createView.groupDateHint', {
                  start: formatDateLabel(eventMinDate!.toString()),
                  end: formatDateLabel(eventMaxDate!.toString()),
                })
              }}
            </p>

            <!-- Date mode selection -->
            <RadioGroup v-model="dateMode" data-testid="input-task-date-mode" class="flex gap-4">
              <div class="flex items-center gap-2">
                <RadioGroupItem value="single" id="dm-single" />
                <Label for="dm-single">{{ t('duties.tasks.createView.dateMode.single') }}</Label>
              </div>
              <div class="flex items-center gap-2">
                <RadioGroupItem value="range" id="dm-range" />
                <Label for="dm-range">{{ t('duties.tasks.createView.dateMode.range') }}</Label>
              </div>
              <div class="flex items-center gap-2">
                <RadioGroupItem value="specific" id="dm-specific" />
                <Label for="dm-specific">{{
                  t('duties.tasks.createView.dateMode.specific')
                }}</Label>
              </div>
            </RadioGroup>

            <!-- Single date -->
            <div v-if="dateMode === 'single'" class="space-y-2">
              <Label>{{ t('duties.shifts.fields.date') }} *</Label>
              <DatePicker
                v-model="singleDate"
                :min-value="eventMinDate"
                :max-value="eventMaxDate"
              />
            </div>

            <!-- Date range -->
            <div v-if="dateMode === 'range'" class="grid grid-cols-2 gap-4">
              <div class="space-y-2">
                <Label>{{ t('duties.tasks.fields.startDate') }} *</Label>
                <DatePicker
                  v-model="rangeStartDate"
                  :min-value="eventMinDate"
                  :max-value="rangeEndDate ?? eventMaxDate"
                />
              </div>
              <div class="space-y-2">
                <Label>{{ t('duties.tasks.fields.endDate') }} *</Label>
                <DatePicker
                  v-model="rangeEndDate"
                  :min-value="rangeStartDate ?? eventMinDate"
                  :max-value="eventMaxDate"
                  :highlight="rangeStartDate"
                />
              </div>
            </div>

            <!-- Specific dates -->
            <div v-if="dateMode === 'specific'" class="space-y-3">
              <div class="flex items-end gap-3">
                <div class="flex-1 space-y-2">
                  <Label>{{ t('duties.tasks.createView.addDate') }}</Label>
                  <DatePicker
                    v-model="specificDatePicker"
                    :min-value="eventMinDate"
                    :max-value="eventMaxDate"
                  />
                </div>
                <Button :disabled="!specificDatePicker" @click="addSpecificDate">
                  <Plus class="mr-1.5 h-4 w-4" />
                  {{ t('duties.tasks.createView.addDate') }}
                </Button>
              </div>
              <div
                v-if="specificDates.length === 0"
                class="py-4 text-center text-sm text-muted-foreground"
              >
                {{ t('duties.tasks.createView.noDatesSelected') }}
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
                    :aria-label="
                      t('duties.tasks.createView.removeDate', {
                        date: formatDateLabel(date.toString()),
                      })
                    "
                    @click="removeSpecificDate(index)"
                  >
                    <X class="h-3 w-3" />
                  </button>
                </Badge>
              </div>
            </div>

            <div class="flex justify-end pt-2">
              <Button :disabled="!isCurrentSectionValid" @click="goToNext">{{
                t('common.actions.next')
              }}</Button>
            </div>
          </div>
        </AccordionContent>
      </AccordionItem>

      <!-- Section 4: Schedule & Shifts -->
      <AccordionItem value="schedule" data-testid="section-schedule" class="rounded-lg border">
        <AccordionTrigger class="px-6 hover:no-underline">
          <div class="flex items-center gap-3">
            <Clock class="h-5 w-5 text-primary" />
            <div class="text-left">
              <p class="font-semibold">{{ t('duties.tasks.createView.sections.schedule') }}</p>
              <p class="text-sm text-muted-foreground">
                {{ t('duties.tasks.createView.sections.scheduleDesc') }}
              </p>
            </div>
          </div>
        </AccordionTrigger>
        <AccordionContent class="px-6 pb-6">
          <div class="space-y-6">
            <ScheduleConfigForm
              v-model:default-start-time="defaultStartTime"
              v-model:default-end-time="defaultEndTime"
              v-model:shift-duration-minutes="shiftDurationMinutes"
              v-model:people-per-shift="peoplePerShift"
              v-model:remainder-mode="remainderMode"
              v-model:overrides="overrides"
              :has-remainder="hasRemainder"
              :available-dates="availableDates"
              :show-overrides="dateMode !== 'single'"
              :event-start-time="selectedEvent?.default_start_time ?? null"
              :event-end-time="selectedEvent?.default_end_time ?? null"
            />

            <div class="flex justify-end pt-2">
              <Button :disabled="!isCurrentSectionValid" @click="goToNext">{{
                t('common.actions.next')
              }}</Button>
            </div>
          </div>
        </AccordionContent>
      </AccordionItem>

      <!-- Section 5: Preview -->
      <AccordionItem value="preview" data-testid="section-preview" class="rounded-lg border">
        <AccordionTrigger class="px-6 hover:no-underline">
          <div class="flex items-center gap-3">
            <CalendarPlus class="h-5 w-5 text-primary" />
            <div class="text-left">
              <p class="font-semibold">{{ t('duties.tasks.createView.sections.preview') }}</p>
              <p class="text-sm text-muted-foreground">
                {{ t('duties.tasks.createView.sections.previewDesc') }}
              </p>
            </div>
            <Badge v-if="totalShifts > 0" variant="secondary" class="ml-2">
              {{
                t('duties.tasks.createView.preview.summary', {
                  shifts: totalShifts,
                  days: totalDays,
                })
              }}
            </Badge>
          </div>
        </AccordionTrigger>
        <AccordionContent class="px-6 pb-6">
          <div
            v-if="totalShifts === 0"
            data-testid="preview-summary"
            class="py-8 text-center text-muted-foreground"
          >
            {{ t('duties.tasks.createView.preview.noShifts') }}
          </div>
          <div v-else class="space-y-4">
            <p data-testid="preview-summary" class="text-sm font-medium text-muted-foreground">
              {{
                t('duties.tasks.createView.preview.summary', {
                  shifts: totalShifts,
                  days: totalDays,
                })
              }}
            </p>
            <p class="text-sm text-muted-foreground">
              {{ t('duties.tasks.createView.preview.clickToExclude') }}
            </p>
            <ShiftPreviewGrid
              :shifts-by-date="shiftsByDate"
              :is-shift-excluded="isShiftExcluded"
              @toggle-exclusion="toggleShiftExclusion"
            />
          </div>
          <div class="mt-4 flex justify-end gap-3">
            <Button
              data-testid="btn-cancel"
              variant="outline"
              @click="router.push({ name: 'tasks' })"
            >
              {{ t('common.actions.cancel') }}
            </Button>
            <Button
              data-testid="btn-submit"
              :disabled="!isValid || submitting"
              @click="handleSubmit"
            >
              <CalendarPlus class="mr-2 h-4 w-4" />
              {{ submitting ? t('common.states.saving') : t('duties.tasks.createView.submit') }}
            </Button>
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  </div>
</template>
