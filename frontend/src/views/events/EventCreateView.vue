<script setup lang="ts">
import { computed, onMounted, ref, toRaw, watch } from 'vue'

import type { DateValue } from '@internationalized/date'
import { parseDate } from '@internationalized/date'
import { ArrowLeft, CalendarDays, CalendarPlus, Clock, Plus, Users, X } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useFormatters } from '@/composables/useFormatters'
import {
  type RemainderMode,
  type ScheduleConfig,
  useSlotPreview,
} from '@/composables/useSlotPreview'

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

import ScheduleConfigForm from '@/components/events/ScheduleConfigForm.vue'
import SlotPreviewGrid from '@/components/events/SlotPreviewGrid.vue'

import type { EventGroupListResponse, EventGroupRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const { t } = useI18n()
const { formatDateLabel } = useFormatters()
const route = useRoute()
const router = useRouter()
const { get, post } = useAuthenticatedClient()

// Prefill event group from query param (e.g. when creating from EventGroupDetailView)
const prefillGroupId = route.query.groupId as string | undefined

// --- Form state ---
const name = ref('')
const description = ref('')
const location = ref('')
const category = ref('')

// Event group
const eventGroupMode = ref<'none' | 'existing' | 'new'>('none')
const selectedEventGroupId = ref<string>('')
const eventGroups = ref<EventGroupRead[]>([])
const newGroupName = ref('')
const newGroupDescription = ref('')
const newGroupStartDate = ref<DateValue>()
const newGroupEndDate = ref<DateValue>()

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

// Date constraints from event group
const selectedGroup = computed(() => {
  if (eventGroupMode.value === 'existing' && selectedEventGroupId.value) {
    return eventGroups.value.find((g) => g.id === selectedEventGroupId.value)
  }
  return null
})

const groupMinDate = computed(() => {
  if (selectedGroup.value) return parseDate(selectedGroup.value.start_date)
  if (eventGroupMode.value === 'new' && newGroupStartDate.value) return newGroupStartDate.value
  return undefined
})

const groupMaxDate = computed(() => {
  if (selectedGroup.value) return parseDate(selectedGroup.value.end_date)
  if (eventGroupMode.value === 'new' && newGroupEndDate.value) return newGroupEndDate.value
  return undefined
})

const hasGroupDateConstraint = computed(() => !!groupMinDate.value && !!groupMaxDate.value)

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

// Clear dates when group changes (constraints may have changed)
watch([eventGroupMode, selectedEventGroupId], () => {
  singleDate.value = undefined
  rangeStartDate.value = undefined
  rangeEndDate.value = undefined
  specificDates.value = []
})

// Schedule
const defaultStartTime = ref('10:00')
const defaultEndTime = ref('18:00')
const slotDurationMinutes = ref(30)
const peoplePerSlot = ref(2)
const remainderMode = ref<RemainderMode>('drop')
const overrides = ref<Array<{ date: string; startTime: string; endTime: string }>>([])

// UI state
const submitting = ref(false)
const activeSection = ref('details')

const sections = ['details', 'eventGroup', 'dates', 'schedule', 'preview'] as const

const isDetailsValid = computed(() => {
  return !!name.value.trim()
})

const isEventGroupValid = computed(() => {
  if (eventGroupMode.value === 'existing') return !!selectedEventGroupId.value
  if (eventGroupMode.value === 'new') {
    return !!newGroupName.value.trim() && !!newGroupStartDate.value && !!newGroupEndDate.value
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
  return !!defaultStartTime.value && !!defaultEndTime.value && slotDurationMinutes.value >= 1
})

const sectionValid: Record<string, () => boolean> = {
  details: () => isDetailsValid.value,
  eventGroup: () => isEventGroupValid.value,
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

// --- Slot preview ---
const scheduleConfig = computed<ScheduleConfig>(() => ({
  eventName: name.value || 'Event',
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

// --- Date sync ---
watch(rangeStartDate, (val) => {
  if (val && rangeEndDate.value && rangeEndDate.value.compare(val) < 0) {
    rangeEndDate.value = undefined
  }
})

// --- Load event groups ---
const loadEventGroups = async () => {
  try {
    const response = await get<{ data: EventGroupListResponse }>({
      url: '/event-groups/',
      query: { limit: 100 },
    })
    eventGroups.value = response.data.items

    // Prefill event group selection if groupId query param is present
    if (prefillGroupId && eventGroups.value.some((g) => g.id === prefillGroupId)) {
      eventGroupMode.value = 'existing'
      selectedEventGroupId.value = prefillGroupId
    }
  } catch {
    // Non-critical, just won't have groups to select from
  }
}

onMounted(loadEventGroups)

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

// --- Form validation ---
const isValid = computed(() => {
  return (
    isDetailsValid.value &&
    isEventGroupValid.value &&
    isDatesValid.value &&
    isScheduleValid.value &&
    totalSlots.value > 0
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
        excluded_slots: Array.from(excludedSlots.value).map((key) => {
          const [date, start_time, end_time] = key.split('|')
          return { date, start_time: start_time + ':00', end_time: end_time + ':00' }
        }),
      },
    }

    if (eventGroupMode.value === 'existing' && selectedEventGroupId.value) {
      body.event_group_id = selectedEventGroupId.value
    } else if (eventGroupMode.value === 'new') {
      body.new_event_group = {
        name: newGroupName.value,
        description: newGroupDescription.value || null,
        start_date: newGroupStartDate.value!.toString(),
        end_date: newGroupEndDate.value!.toString(),
      }
    }

    const response = await post<{ data: { event: { id: string }; duty_slots_created: number } }>({
      url: '/events/with-slots',
      body,
    })

    toast.success(
      t('duties.events.createView.success', { count: response.data.duty_slots_created }),
    )
    router.push({ name: 'event-detail', params: { eventId: response.data.event.id } })
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
      <Button data-testid="btn-back" variant="ghost" size="sm" class="-ml-2" @click="router.push({ name: 'events' })">
        <ArrowLeft class="mr-1.5 h-4 w-4" />
        {{ t('common.actions.back') }}
      </Button>
      <h1 data-testid="page-heading" class="text-3xl font-bold">{{ t('duties.events.createView.title') }}</h1>
      <p class="text-muted-foreground">{{ t('duties.events.createView.subtitle') }}</p>
    </div>

    <Accordion v-model="activeSection" type="single" collapsible class="space-y-4">
      <!-- Section 1: Event Details -->
      <AccordionItem value="details" data-testid="section-event-details" class="rounded-lg border">
        <AccordionTrigger class="px-6 hover:no-underline">
          <div class="flex items-center gap-3">
            <CalendarPlus class="h-5 w-5 text-primary" />
            <div class="text-left">
              <p class="font-semibold">{{ t('duties.events.createView.sections.details') }}</p>
              <p class="text-sm text-muted-foreground">
                {{ t('duties.events.createView.sections.detailsDesc') }}
              </p>
            </div>
          </div>
        </AccordionTrigger>
        <AccordionContent class="px-6 pb-6">
          <div class="space-y-4">
            <div class="space-y-2">
              <Label>{{ t('duties.events.fields.name') }} *</Label>
              <Input v-model="name" data-testid="input-event-name" />
            </div>
            <div class="space-y-2">
              <Label>{{ t('duties.events.fields.description') }}</Label>
              <Textarea v-model="description" :rows="3" />
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
            <div class="flex justify-end pt-2">
              <Button :disabled="!isCurrentSectionValid" @click="goToNext">{{
                t('common.actions.next')
              }}</Button>
            </div>
          </div>
        </AccordionContent>
      </AccordionItem>

      <!-- Section 2: Event Group -->
      <AccordionItem value="eventGroup" data-testid="section-event-group" class="rounded-lg border">
        <AccordionTrigger class="px-6 hover:no-underline">
          <div class="flex items-center gap-3">
            <Users class="h-5 w-5 text-primary" />
            <div class="text-left">
              <p class="font-semibold">{{ t('duties.events.createView.sections.eventGroup') }}</p>
              <p class="text-sm text-muted-foreground">
                {{ t('duties.events.createView.sections.eventGroupDesc') }}
              </p>
            </div>
          </div>
        </AccordionTrigger>
        <AccordionContent class="px-6 pb-6">
          <RadioGroup v-model="eventGroupMode" class="space-y-3">
            <div class="flex items-center gap-2">
              <RadioGroupItem value="none" id="eg-none" />
              <Label for="eg-none">{{ t('duties.events.createView.eventGroupOption.none') }}</Label>
            </div>
            <div class="flex items-center gap-2">
              <RadioGroupItem value="existing" id="eg-existing" />
              <Label for="eg-existing">{{
                t('duties.events.createView.eventGroupOption.existing')
              }}</Label>
            </div>
            <div class="flex items-center gap-2">
              <RadioGroupItem value="new" id="eg-new" />
              <Label for="eg-new">{{ t('duties.events.createView.eventGroupOption.new') }}</Label>
            </div>
          </RadioGroup>

          <!-- Select existing group -->
          <div v-if="eventGroupMode === 'existing'" class="mt-4">
            <Select v-model="selectedEventGroupId">
              <SelectTrigger>
                <SelectValue
                  :placeholder="t('duties.events.createView.eventGroupOption.existing')"
                />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="group in eventGroups" :key="group.id" :value="group.id">
                  {{ group.name }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <!-- Create new group -->
          <div v-if="eventGroupMode === 'new'" class="mt-4 space-y-4 rounded-md border p-4">
            <div class="space-y-2">
              <Label>{{ t('duties.eventGroups.fields.name') }} *</Label>
              <Input v-model="newGroupName" />
            </div>
            <div class="space-y-2">
              <Label>{{ t('duties.eventGroups.fields.description') }}</Label>
              <Input v-model="newGroupDescription" />
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div class="space-y-2">
                <Label>{{ t('duties.eventGroups.fields.startDate') }} *</Label>
                <DatePicker v-model="newGroupStartDate" :max-value="newGroupEndDate" />
              </div>
              <div class="space-y-2">
                <Label>{{ t('duties.eventGroups.fields.endDate') }} *</Label>
                <DatePicker
                  v-model="newGroupEndDate"
                  :min-value="newGroupStartDate"
                  :highlight="newGroupStartDate"
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

      <!-- Section 3: Event Dates -->
      <AccordionItem value="dates" data-testid="section-event-dates" class="rounded-lg border">
        <AccordionTrigger class="px-6 hover:no-underline">
          <div class="flex items-center gap-3">
            <CalendarDays class="h-5 w-5 text-primary" />
            <div class="text-left">
              <p class="font-semibold">{{ t('duties.events.createView.sections.dates') }}</p>
              <p class="text-sm text-muted-foreground">
                {{ t('duties.events.createView.sections.datesDesc') }}
              </p>
            </div>
          </div>
        </AccordionTrigger>
        <AccordionContent class="px-6 pb-6">
          <div class="space-y-4">
            <!-- Group date constraint hint -->
            <p v-if="hasGroupDateConstraint" class="text-sm text-muted-foreground">
              {{
                t('duties.events.createView.groupDateHint', {
                  start: formatDateLabel(groupMinDate!.toString()),
                  end: formatDateLabel(groupMaxDate!.toString()),
                })
              }}
            </p>

            <!-- Date mode selection -->
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
                <Label for="dm-specific">{{
                  t('duties.events.createView.dateMode.specific')
                }}</Label>
              </div>
            </RadioGroup>

            <!-- Single date -->
            <div v-if="dateMode === 'single'" class="space-y-2">
              <Label>{{ t('duties.dutySlots.fields.date') }} *</Label>
              <DatePicker
                v-model="singleDate"
                :min-value="groupMinDate"
                :max-value="groupMaxDate"
              />
            </div>

            <!-- Date range -->
            <div v-if="dateMode === 'range'" class="grid grid-cols-2 gap-4">
              <div class="space-y-2">
                <Label>{{ t('duties.events.fields.startDate') }} *</Label>
                <DatePicker
                  v-model="rangeStartDate"
                  :min-value="groupMinDate"
                  :max-value="rangeEndDate ?? groupMaxDate"
                />
              </div>
              <div class="space-y-2">
                <Label>{{ t('duties.events.fields.endDate') }} *</Label>
                <DatePicker
                  v-model="rangeEndDate"
                  :min-value="rangeStartDate ?? groupMinDate"
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

            <div class="flex justify-end pt-2">
              <Button :disabled="!isCurrentSectionValid" @click="goToNext">{{
                t('common.actions.next')
              }}</Button>
            </div>
          </div>
        </AccordionContent>
      </AccordionItem>

      <!-- Section 4: Schedule & Slots -->
      <AccordionItem value="schedule" data-testid="section-schedule" class="rounded-lg border">
        <AccordionTrigger class="px-6 hover:no-underline">
          <div class="flex items-center gap-3">
            <Clock class="h-5 w-5 text-primary" />
            <div class="text-left">
              <p class="font-semibold">{{ t('duties.events.createView.sections.schedule') }}</p>
              <p class="text-sm text-muted-foreground">
                {{ t('duties.events.createView.sections.scheduleDesc') }}
              </p>
            </div>
          </div>
        </AccordionTrigger>
        <AccordionContent class="px-6 pb-6">
          <div class="space-y-6">
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
              <p class="font-semibold">{{ t('duties.events.createView.sections.preview') }}</p>
              <p class="text-sm text-muted-foreground">
                {{ t('duties.events.createView.sections.previewDesc') }}
              </p>
            </div>
            <Badge v-if="totalSlots > 0" variant="secondary" class="ml-2">
              {{
                t('duties.events.createView.preview.summary', {
                  slots: totalSlots,
                  days: totalDays,
                })
              }}
            </Badge>
          </div>
        </AccordionTrigger>
        <AccordionContent class="px-6 pb-6">
          <div v-if="totalSlots === 0" class="py-8 text-center text-muted-foreground">
            {{ t('duties.events.createView.preview.noSlots') }}
          </div>
          <div v-else class="space-y-4">
            <p class="text-sm font-medium text-muted-foreground">
              {{
                t('duties.events.createView.preview.summary', {
                  slots: totalSlots,
                  days: totalDays,
                })
              }}
            </p>
            <p class="text-sm text-muted-foreground">
              {{ t('duties.events.createView.preview.clickToExclude') }}
            </p>
            <SlotPreviewGrid
              :slots-by-date="slotsByDate"
              :is-slot-excluded="isSlotExcluded"
              @toggle-exclusion="toggleSlotExclusion"
            />
          </div>
          <div class="mt-4 flex justify-end gap-3">
            <Button data-testid="btn-cancel" variant="outline" @click="router.push({ name: 'events' })">
              {{ t('common.actions.cancel') }}
            </Button>
            <Button data-testid="btn-submit" :disabled="!isValid || submitting" @click="handleSubmit">
              <CalendarPlus class="mr-2 h-4 w-4" />
              {{ submitting ? t('common.states.saving') : t('duties.events.createView.submit') }}
            </Button>
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  </div>
</template>
