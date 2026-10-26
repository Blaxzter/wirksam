<script setup lang="ts">
import { computed, onMounted, ref, toRaw, watch } from 'vue'

import type { DateValue } from '@internationalized/date'
import { parseDate } from '@internationalized/date'
import { ArrowLeft, CalendarDays, CalendarPlus, Clock, Plus, X } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'
import { useBreadcrumbStore } from '@/stores/breadcrumb'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useFormatters } from '@/composables/useFormatters'
import {
  type RemainderMode,
  type ScheduleConfig,
  eachDateInRange,
  useShiftPreview,
} from '@/composables/useShiftPreview'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent } from '@/components/ui/card'
import { CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { DatePicker } from '@/components/ui/date-picker'
import Input from '@/components/ui/input/Input.vue'
import Label from '@/components/ui/label/Label.vue'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'

import LocationPicker from '@/components/locations/LocationPicker.vue'
import ScheduleConfigForm from '@/components/tasks/ScheduleConfigForm.vue'
import ShiftPreviewGrid from '@/components/tasks/ShiftPreviewGrid.vue'

import type { EventRead, TaskRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const { t } = useI18n()
const { formatTime, formatDateLabel } = useFormatters()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const breadcrumbStore = useBreadcrumbStore()
const { get, post } = useAuthenticatedClient()

const eventId = computed(() => route.params.eventId as string)
const loading = ref(true)
const submitting = ref(false)
const task = ref<TaskRead | null>(null)
const event = ref<EventRead | null>(null)

// --- Task event date constraints ---
const eventMinDate = computed(() => (event.value ? parseDate(event.value.start_date) : undefined))
const eventMaxDate = computed(() => (event.value ? parseDate(event.value.end_date) : undefined))

// --- Batch-specific fields ---
const location = ref('')
const locationId = ref<string | null>(null)
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
const shiftDurationMinutes = ref(30)
const peoplePerShift = ref(2)
const remainderMode = ref<RemainderMode>('drop')
const overrides = ref<Array<{ date: string; startTime: string; endTime: string }>>([])

// --- Shift preview ---
const scheduleConfig = computed<ScheduleConfig>(() => ({
  eventName: task.value?.name || 'Task',
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

  return eachDateInRange(startDate.value.toString(), endDate.value.toString()).filter(
    (dateStr) => !overrides.value.some((o) => o.date === dateStr),
  )
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
    shiftDurationMinutes.value >= 1 &&
    totalShifts.value > 0
  )
})

// --- Load task ---
const loadTask = async () => {
  loading.value = true
  try {
    const response = await get<{ data: TaskRead }>({
      url: `/tasks/${eventId.value}`,
    })
    task.value = response.data
    const ev = response.data

    // Check if user can manage this task
    if (!authStore.canManageEvent(ev.event_id)) {
      router.replace({ name: 'task-detail', params: { eventId: eventId.value } })
      return
    }

    // Fetch task event for date constraints
    if (ev.event_id) {
      try {
        const groupResponse = await get<{ data: EventRead }>({
          url: `/events/${ev.event_id}`,
        })
        event.value = groupResponse.data
      } catch {
        // Non-critical — continue without constraints
      }
    }

    // Pre-fill from task defaults
    location.value = ev.location ?? ''
    locationId.value = ev.location_id ?? null
    category.value = ev.category ?? ''
    if (ev.default_start_time) defaultStartTime.value = formatTime(ev.default_start_time)
    if (ev.default_end_time) defaultEndTime.value = formatTime(ev.default_end_time)
    if (ev.shift_duration_minutes) shiftDurationMinutes.value = ev.shift_duration_minutes
    if (ev.people_per_shift) peoplePerShift.value = ev.people_per_shift

    breadcrumbStore.setBreadcrumbs([
      { title: 'Tasks', titleKey: 'duties.tasks.title', to: { name: 'tasks' } },
      { title: ev.name, to: { name: 'task-detail', params: { eventId: ev.id } } },
      { title: t('duties.tasks.addShiftsView.title') },
    ])
  } catch (error) {
    toastApiError(error)
    router.push({ name: 'tasks' })
  } finally {
    loading.value = false
  }
}

// --- Submit ---
const handleSubmit = async () => {
  if (!isValid.value || submitting.value) return
  submitting.value = true

  try {
    const response = await post<{ data: { shifts_added: number } }>({
      url: `/tasks/${eventId.value}/add-shifts`,
      body: {
        start_date: startDate.value!.toString(),
        end_date: endDate.value!.toString(),
        location_id: locationId.value,
        location: location.value || null,
        category: category.value || null,
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
          excluded_shifts: [...excludedShifts.value].map((key) => {
            const [date, start_time, end_time] = key.split('|')
            return { date, start_time: start_time + ':00', end_time: end_time + ':00' }
          }),
          // Without this the backend walks every day between start_date and
          // end_date, so the gap days between hand-picked dates get shifts the
          // preview never showed (#144).
          specific_dates:
            dateMode.value === 'specific' ? specificDates.value.map((d) => d.toString()) : null,
        },
      },
    })

    toast.success(t('duties.tasks.addShiftsView.success', { count: response.data.shifts_added }))
    router.push({ name: 'task-detail', params: { eventId: eventId.value } })
  } catch (error) {
    toastApiError(error)
  } finally {
    submitting.value = false
  }
}

onMounted(loadTask)
</script>

<template>
  <div class="mx-auto max-w-3xl space-y-6">
    <!-- Loading -->
    <div v-if="loading" class="text-center py-12 text-muted-foreground">
      {{ t('common.states.loading') }}
    </div>

    <template v-else-if="task">
      <!-- Header -->
      <div class="space-y-2">
        <Button
          data-testid="btn-back"
          variant="ghost"
          size="sm"
          class="-ml-2 max-xl:hidden"
          @click="router.push({ name: 'task-detail', params: { eventId: eventId } })"
        >
          <ArrowLeft class="mr-1.5 h-4 w-4" />
          {{ t('common.actions.back') }}
        </Button>
        <h1 data-testid="page-heading" class="text-2xl sm:text-3xl font-bold">
          {{ t('duties.tasks.addShiftsView.title') }}
        </h1>
        <p class="text-muted-foreground">
          {{ t('duties.tasks.addShiftsView.subtitle') }}
          <span class="font-medium text-foreground">{{ task.name }}</span>
        </p>
      </div>

      <!-- Batch Details (location / category) -->
      <Card data-testid="section-batch">
        <CardHeader>
          <CardTitle>{{ t('duties.tasks.addShiftsView.sections.batch') }}</CardTitle>
          <CardDescription>{{
            t('duties.tasks.addShiftsView.sections.batchDesc')
          }}</CardDescription>
        </CardHeader>
        <CardContent>
          <div class="grid items-start gap-4 sm:grid-cols-2">
            <div class="space-y-2">
              <Label for="batch-location">{{ t('duties.tasks.fields.location') }}</Label>
              <LocationPicker
                v-model:location-id="locationId"
                v-model:text="location"
                :event-id="task?.event_id"
                input-id="batch-location"
              />
            </div>
            <div class="space-y-2">
              <Label>{{ t('duties.tasks.fields.category') }}</Label>
              <Input v-model="category" />
            </div>
          </div>
        </CardContent>
      </Card>

      <!-- Dates -->
      <Card data-testid="section-task-dates">
        <CardHeader>
          <div class="flex items-center gap-3">
            <CalendarDays class="h-5 w-5 text-primary" />
            <div>
              <CardTitle>{{ t('duties.tasks.createView.sections.dates') }}</CardTitle>
              <CardDescription>{{
                t('duties.tasks.createView.sections.datesDesc')
              }}</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent class="space-y-4">
          <RadioGroup v-model="dateMode" class="flex gap-4">
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
              <Label for="dm-specific">{{ t('duties.tasks.createView.dateMode.specific') }}</Label>
            </div>
          </RadioGroup>

          <!-- Single date -->
          <div v-if="dateMode === 'single'" class="space-y-2">
            <Label>{{ t('duties.shifts.fields.date') }} *</Label>
            <DatePicker v-model="singleDate" :min-value="eventMinDate" :max-value="eventMaxDate" />
          </div>

          <!-- Date range -->
          <div v-if="dateMode === 'range'" class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <Label>{{ t('duties.tasks.fields.startDate') }} *</Label>
              <DatePicker
                v-model="rangeStartDate"
                :min-value="eventMinDate"
                :max-value="rangeEndDate || eventMaxDate"
              />
            </div>
            <div class="space-y-2">
              <Label>{{ t('duties.tasks.fields.endDate') }} *</Label>
              <DatePicker
                v-model="rangeEndDate"
                :min-value="rangeStartDate || eventMinDate"
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
        </CardContent>
      </Card>

      <!-- Schedule -->
      <Card data-testid="section-schedule">
        <CardHeader>
          <div class="flex items-center gap-3">
            <Clock class="h-5 w-5 text-primary" />
            <div>
              <CardTitle>{{ t('duties.tasks.createView.sections.schedule') }}</CardTitle>
              <CardDescription>{{
                t('duties.tasks.createView.sections.scheduleDesc')
              }}</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent class="space-y-6">
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
            :event-start-time="event?.default_start_time ?? null"
            :event-end-time="event?.default_end_time ?? null"
          />
        </CardContent>
      </Card>

      <!-- Preview -->
      <Card data-testid="section-preview">
        <CardHeader>
          <div class="flex items-center justify-between">
            <div>
              <CardTitle>{{ t('duties.tasks.createView.sections.preview') }}</CardTitle>
              <CardDescription>{{
                t('duties.tasks.createView.sections.previewDesc')
              }}</CardDescription>
            </div>
            <Badge v-if="totalShifts > 0" variant="secondary">
              {{
                t('duties.tasks.createView.preview.summary', {
                  shifts: totalShifts,
                  days: totalDays,
                })
              }}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div v-if="totalShifts === 0" class="py-8 text-center text-muted-foreground">
            {{ t('duties.tasks.createView.preview.noShifts') }}
          </div>
          <div v-else>
            <ShiftPreviewGrid
              :shifts-by-date="shiftsByDate"
              :is-shift-excluded="isShiftExcluded"
              @toggle-exclusion="toggleShiftExclusion"
            />
          </div>
        </CardContent>
      </Card>

      <!-- Actions -->
      <div class="flex justify-end gap-3">
        <Button
          data-testid="btn-cancel"
          variant="outline"
          @click="router.push({ name: 'task-detail', params: { eventId: eventId } })"
        >
          {{ t('common.actions.cancel') }}
        </Button>
        <Button data-testid="btn-submit" :disabled="!isValid || submitting" @click="handleSubmit">
          <CalendarPlus class="mr-2 h-4 w-4" />
          {{ submitting ? t('common.states.saving') : t('duties.tasks.addShiftsView.submit') }}
        </Button>
      </div>
    </template>
  </div>
</template>
