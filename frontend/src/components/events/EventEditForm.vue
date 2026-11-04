<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import type { DateValue } from '@internationalized/date'
import { parseDate } from '@internationalized/date'
import { Archive, CalendarClock, Check, FilePen, MoveRight, Send, X } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import EventOptionCards from '@/components/events/EventOptionCards.vue'
import EventTimezonePicker from '@/components/events/EventTimezonePicker.vue'
import EventVisibilityPicker from '@/components/events/EventVisibilityPicker.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { MarkerVariant } from '@/components/ui/calendar'
import { DatePicker } from '@/components/ui/date-picker'
import Input from '@/components/ui/input/Input.vue'
import Label from '@/components/ui/label/Label.vue'
import Separator from '@/components/ui/separator/Separator.vue'
import Textarea from '@/components/ui/textarea/Textarea.vue'
import { TimePicker } from '@/components/ui/time-picker'

import type { EventRead, TaskRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import type { EventVisibility } from '@/lib/event-roles'
import { formatDate } from '@/lib/format'
import { timeZoneLabel } from '@/lib/timezones'

const props = defineProps<{
  event: EventRead
  eventId: string
  tasks: TaskRead[]
}>()

const emit = defineEmits<{
  updated: [event: EventRead]
  cancel: []
}>()

const { t } = useI18n()
const { get, patch, post } = useAuthenticatedClient()

// ── Edit form state ──
const name = ref(props.event.name)
const description = ref(props.event.description ?? '')
const startDate = ref<DateValue>()
const endDate = ref<DateValue>()
const startTime = ref(props.event.default_start_time?.slice(0, 5) ?? '')
const endTime = ref(props.event.default_end_time?.slice(0, 5) ?? '')
const timezone = ref(props.event.timezone)
const status = ref(props.event.status ?? 'draft')
const visibility = ref<EventVisibility>(props.event.visibility ?? 'private')
const saving = ref(false)

const statusOptions = computed(() => [
  {
    value: 'draft' as const,
    label: t('duties.events.statuses.draft'),
    hint: t('duties.events.statusHints.draft'),
    icon: FilePen,
  },
  {
    value: 'published' as const,
    label: t('duties.events.statuses.published'),
    hint: t('duties.events.statusHints.published'),
    icon: Send,
  },
  {
    value: 'archived' as const,
    label: t('duties.events.statuses.archived'),
    hint: t('duties.events.statusHints.archived'),
    icon: Archive,
  },
])

// Default time window must satisfy end > start when both set (overnight wrap
// is not supported — see issue #85).
const defaultTimesError = computed<string | null>(() => {
  if (!startTime.value || !endTime.value) return null
  if (endTime.value <= startTime.value) {
    return t('duties.events.fields.defaultTimesInvalid')
  }
  return null
})

// Task date bounds for constraining pickers
const earliestTaskDate = ref<DateValue>()
const latestTaskDate = ref<DateValue>()
const hasTasks = computed(() => !!earliestTaskDate.value)

function toLocalIso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// Markers: task start dates (green), end dates (red), other task days (default dot), today (blue)
const eventMarkers = computed(() => {
  const markers = new Map<string, MarkerVariant>()
  const todayIso = toLocalIso(new Date())
  for (const ev of props.tasks) {
    const isSingleDay = ev.start_date === ev.end_date
    // Fill range with default dots
    const start = new Date(ev.start_date + 'T00:00:00')
    const end = new Date(ev.end_date + 'T00:00:00')
    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
      if (!markers.has(toLocalIso(d))) markers.set(toLocalIso(d), 'default')
    }
    // Multi-day tasks get colored start/end dots
    if (!isSingleDay) {
      markers.set(ev.start_date, 'start')
      markers.set(ev.end_date, 'end')
    }
  }
  if (!markers.has(todayIso)) markers.set(todayIso, 'today')
  return markers
})

// ── Shift dates state ──
const shiftTargetDate = ref<DateValue>()
const shifting = ref(false)

const shiftDays = computed(() => {
  if (!shiftTargetDate.value || !startDate.value) return 0
  return shiftTargetDate.value.compare(parseDate(props.event.start_date))
})

async function loadTaskDateBounds() {
  try {
    const res = await get<{ data: { earliest_start: string | null; latest_end: string | null } }>({
      url: `/events/${props.eventId}/task-date-bounds`,
    })
    earliestTaskDate.value = res.data.earliest_start
      ? parseDate(res.data.earliest_start)
      : undefined
    latestTaskDate.value = res.data.latest_end ? parseDate(res.data.latest_end) : undefined
  } catch {
    // Non-critical
  }
}

async function handleSubmit() {
  if (!startDate.value || !endDate.value || !name.value.trim()) return
  if (defaultTimesError.value) return
  saving.value = true
  try {
    const res = await patch<{ data: EventRead }>({
      url: `/events/${props.eventId}`,
      body: {
        name: name.value.trim(),
        description: description.value.trim() || null,
        start_date: startDate.value.toString(),
        end_date: endDate.value.toString(),
        timezone: timezone.value,
        status: status.value,
        visibility: visibility.value,
        default_start_time: startTime.value ? `${startTime.value}:00` : null,
        default_end_time: endTime.value ? `${endTime.value}:00` : null,
      },
    })
    emit('updated', res.data)
    toast.success(t('duties.events.detail.updated'))
  } catch (error) {
    toastApiError(error)
  } finally {
    saving.value = false
  }
}

async function handleShiftDates() {
  if (!shiftTargetDate.value || shiftDays.value === 0) return
  shifting.value = true
  try {
    const res = await post<{ data: EventRead }>({
      url: `/events/${props.eventId}/shift-dates`,
      body: { new_start_date: shiftTargetDate.value.toString() },
    })
    emit('updated', res.data)
    toast.success(t('duties.events.detail.shiftSuccess'))
  } catch (error) {
    toastApiError(error)
  } finally {
    shifting.value = false
  }
}

onMounted(() => {
  startDate.value = parseDate(props.event.start_date)
  endDate.value = parseDate(props.event.end_date)
  loadTaskDateBounds()
})
</script>

<template>
  <!-- Edit event details -->
  <Card>
    <CardHeader>
      <CardTitle>{{ t('duties.events.edit') }}</CardTitle>
      <CardDescription>{{ t('duties.events.detail.editDescription') }}</CardDescription>
    </CardHeader>
    <CardContent>
      <form class="space-y-4" @submit.prevent="handleSubmit">
        <div class="space-y-2">
          <Label for="event-name">{{ t('duties.events.fields.name') }}</Label>
          <Input id="event-name" v-model="name" required />
        </div>
        <div class="space-y-2">
          <Label for="event-description">{{ t('duties.events.fields.description') }}</Label>
          <Textarea id="event-description" v-model="description" rows="2" />
        </div>
        <div class="space-y-2">
          <Label>{{ t('duties.events.fields.status') }}</Label>
          <EventOptionCards
            v-model="status"
            :options="statusOptions"
            testid-prefix="btn-event-status-"
          />
        </div>
        <div class="space-y-2">
          <Label>{{ t('duties.events.fields.visibility') }}</Label>
          <EventVisibilityPicker v-model="visibility" />
          <p
            v-if="visibility === 'public' && status !== 'published'"
            class="text-xs font-medium text-amber-700 dark:text-amber-400"
            data-testid="public-unpublished-note"
          >
            {{ t('duties.events.detail.publicNotPublished') }}
          </p>
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div class="space-y-1.5">
            <Label>{{ t('duties.events.fields.startDate') }}</Label>
            <DatePicker
              v-model="startDate"
              :max-value="latestTaskDate"
              :markers="eventMarkers"
              :placeholder="t('duties.events.pickDate')"
            />
            <p v-if="earliestTaskDate" class="text-xs text-muted-foreground">
              {{ t('duties.events.detail.earliestTask', { date: formatDate(earliestTaskDate.toString()) }) }}
            </p>
          </div>
          <div class="space-y-1.5">
            <Label>{{ t('duties.events.fields.endDate') }}</Label>
            <DatePicker
              v-model="endDate"
              :min-value="earliestTaskDate"
              :markers="eventMarkers"
              :placeholder="t('duties.events.pickDate')"
            />
            <p v-if="latestTaskDate" class="text-xs text-muted-foreground">
              {{ t('duties.events.detail.latestTask', { date: formatDate(latestTaskDate.toString()) }) }}
            </p>
          </div>
        </div>
        <div v-if="hasTasks" class="space-y-1.5">
          <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span class="flex items-center gap-1.5">
              <span class="size-2 rounded-full bg-green-500" />
              {{ t('duties.events.detail.legend.eventStart') }}
            </span>
            <span class="flex items-center gap-1.5">
              <span class="size-2 rounded-full bg-red-500" />
              {{ t('duties.events.detail.legend.eventEnd') }}
            </span>
            <span class="flex items-center gap-1.5">
              <span class="size-2 rounded-full bg-primary" />
              {{ t('duties.events.detail.legend.eventDay') }}
            </span>
            <span class="flex items-center gap-1.5">
              <span class="size-2 rounded-full bg-blue-500" />
              {{ t('duties.events.detail.legend.today') }}
            </span>
          </div>
          <p class="text-xs text-muted-foreground">
            {{ t('duties.events.detail.dateConstraintHint') }}
          </p>
        </div>
        <div class="space-y-2">
          <Label for="event-timezone">{{ t('duties.events.timezone.label') }}</Label>
          <EventTimezonePicker v-model="timezone" input-id="event-timezone" />
          <p
            v-if="timezone !== event.timezone"
            class="text-xs font-medium text-amber-700 dark:text-amber-400"
            data-testid="timezone-change-note"
          >
            {{ t('duties.events.timezone.changeNote', { zone: timeZoneLabel(timezone) }) }}
          </p>
          <p v-else class="text-xs text-muted-foreground">
            {{ t('duties.events.timezone.hint') }}
          </p>
        </div>
        <div class="space-y-2">
          <Label class="text-sm">{{ t('duties.events.fields.defaultTimes') }}</Label>
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-1">
              <Label class="text-muted-foreground text-xs">{{ t('duties.events.fields.startTime') }}</Label>
              <TimePicker
                v-model="startTime"
                class="w-full"
                :class="defaultTimesError ? 'border-destructive' : ''"
                :placeholder="t('duties.events.fields.timeOptional')"
              />
            </div>
            <div class="space-y-1">
              <Label class="text-muted-foreground text-xs">{{ t('duties.events.fields.endTime') }}</Label>
              <TimePicker
                v-model="endTime"
                class="w-full"
                :class="defaultTimesError ? 'border-destructive' : ''"
                :placeholder="t('duties.events.fields.timeOptional')"
              />
            </div>
          </div>
          <p v-if="defaultTimesError" class="text-destructive text-xs">
            {{ defaultTimesError }}
          </p>
          <p class="text-muted-foreground text-xs">
            {{ t('duties.events.fields.defaultTimesHint') }}
          </p>
        </div>
        <div class="flex items-center gap-2 pt-2">
          <Button type="submit" size="sm" :disabled="saving">
            <Check class="mr-2 h-4 w-4" />
            {{ t('common.actions.save') }}
          </Button>
          <Button type="button" variant="outline" size="sm" :disabled="saving" @click="emit('cancel')">
            <X class="mr-2 h-4 w-4" />
            {{ t('common.actions.cancel') }}
          </Button>
        </div>
      </form>
    </CardContent>
  </Card>

  <!-- Shift dates -->
  <Card v-if="hasTasks">
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <CalendarClock class="h-5 w-5" />
        {{ t('duties.events.detail.shiftDates') }}
      </CardTitle>
      <CardDescription>{{ t('duties.events.detail.shiftDescription') }}</CardDescription>
    </CardHeader>
    <CardContent>
      <div class="space-y-4">
        <div class="space-y-1.5">
          <Label>{{ t('duties.events.detail.shiftNewStart') }}</Label>
          <DatePicker
            v-model="shiftTargetDate"
            :placeholder="t('duties.events.pickDate')"
            :highlight="startDate"
            :markers="eventMarkers"
          />
        </div>
        <p v-if="shiftDays !== 0" class="text-sm text-muted-foreground">
          {{ t('duties.events.detail.shiftPreview', { days: Math.abs(shiftDays), direction: shiftDays > 0 ? t('duties.events.detail.shiftForward') : t('duties.events.detail.shiftBackward') }) }}
        </p>
        <Separator />
        <Button
          size="sm"
          :disabled="shifting || shiftDays === 0"
          @click="handleShiftDates"
        >
          <MoveRight class="mr-2 h-4 w-4" />
          {{ t('duties.events.detail.shiftApply') }}
        </Button>
      </div>
    </CardContent>
  </Card>

</template>
