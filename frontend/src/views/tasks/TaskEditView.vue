<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import type { DateValue } from '@internationalized/date'
import { parseDate } from '@internationalized/date'
import { ArrowLeft, Clock, Info, Lock, RefreshCw } from '@lucide/vue'
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
  slotKey,
  useShiftPreview,
} from '@/composables/useShiftPreview'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { DatePicker } from '@/components/ui/date-picker'
import Input from '@/components/ui/input/Input.vue'
import Label from '@/components/ui/label/Label.vue'
import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'
import Textarea from '@/components/ui/textarea/Textarea.vue'

import TeamPicker from '@/components/events/teams/TeamPicker.vue'
import LocationPicker from '@/components/locations/LocationPicker.vue'
import ScheduleConfigForm from '@/components/tasks/ScheduleConfigForm.vue'
import ShiftPreviewGrid from '@/components/tasks/ShiftPreviewGrid.vue'

import type {
  EventRead,
  ShiftBatchRead,
  ShiftRead,
  ShiftRegenerationResult,
  TaskRead,
} from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const { t } = useI18n()
const { formatTime, formatDateLabel } = useFormatters()
/**
 * A stored time ("10:00:00") as the schedule form's 24-hour "HH:MM". Not
 * `formatTime`: that is for display and gives "10:00 AM" on a 12-hour clock,
 * which the shift preview cannot read, so it would build no shifts at all.
 */
const clockValue = (time: string | null | undefined): string => (time ?? '').slice(0, 5)
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const breadcrumbStore = useBreadcrumbStore()
const { get, post, patch } = useAuthenticatedClient()

const eventId = computed(() => route.params.eventId as string)
const batchId = computed(() => (route.query.batchId as string) || null)
const isBatchMode = computed(() => !!batchId.value)
/** Who can book (the team) is for organisers; people in charge never see it. */
const canAdminEvent = computed(() => authStore.canManageEvent(task.value?.event_id))
const loading = ref(true)
const submitting = ref(false)
const task = ref<TaskRead | null>(null)
const batches = ref<ShiftBatchRead[]>([])
const batch = ref<ShiftBatchRead | null>(null)
const parentEvent = ref<EventRead | null>(null)
/**
 * Dates, schedule and the shift preview all end in regenerating the shifts.
 * A person in charge of a task that earns vouchers may not do that unless the
 * event allows it (`task.voucher_shifts_admin_only`), so they get only the
 * details, which a plain save of the task covers.
 */
const canManageShifts = computed(() => task.value?.can_manage_shifts ?? false)
/**
 * With several batches the shifts belong to the batches, each with its own
 * dates and schedule (and its own edit on the task page). Regenerating the
 * task as a whole would rebuild all of them from one schedule, so the task's
 * own edit offers just the details then.
 */
const severalBatches = computed(() => batches.value.length > 1)
/** Whether this page changes shifts at all, or only the task's details. */
const editsShifts = computed(
  () => canManageShifts.value && (isBatchMode.value || !severalBatches.value),
)

// --- Form state ---
const name = ref('')
const description = ref('')
const location = ref('')
const locationId = ref<string | null>(null)
const category = ref('')
const teamId = ref<string | null>(null)
const startDate = ref<DateValue>()
const endDate = ref<DateValue>()

// Schedule
const defaultStartTime = ref('10:00')
const defaultEndTime = ref('18:00')
const shiftDurationMinutes = ref(30)
const peoplePerShift = ref(2)
const remainderMode = ref<RemainderMode>('drop')
const overrides = ref<Array<{ date: string; startTime: string; endTime: string }>>([])

// Original schedule snapshot (to detect changes)
interface ScheduleSnapshot {
  startDate: string
  endDate: string
  defaultStartTime: string
  defaultEndTime: string
  shiftDurationMinutes: number
  peoplePerShift: number
  overrides: string // JSON-serialized for easy comparison
}
const originalSchedule = ref<ScheduleSnapshot | null>(null)
const originalExcludedShifts = ref<Set<string>>(new Set())

const currentScheduleSnapshot = computed<ScheduleSnapshot | null>(() => {
  if (!startDate.value || !endDate.value) return null
  return {
    startDate: startDate.value.toString(),
    endDate: endDate.value.toString(),
    defaultStartTime: defaultStartTime.value,
    defaultEndTime: defaultEndTime.value,
    shiftDurationMinutes: shiftDurationMinutes.value,
    peoplePerShift: peoplePerShift.value,
    overrides: JSON.stringify(overrides.value),
  }
})

// Affected bookings dialog
const showAffectedDialog = ref(false)

const pendingPreview = ref<ShiftRegenerationResult | null>(null)

/**
 * A person in charge may not remove a shift that has started with people on
 * it; the dry run marks those rows, and the real run would refuse them.
 */
const previewHasLocked = computed(
  () => pendingPreview.value?.affected_bookings.some((b) => b.locked) ?? false,
)

// --- Existing shift bookings (fetched from backend) ---
const existingBookings = ref(new Map<string, number>())

const getShiftBookingCount = (shift: {
  date: string
  startTime: string
  endTime: string
}): number => {
  const key = `${shift.date}|${shift.startTime}|${shift.endTime}`
  return existingBookings.value.get(key) ?? 0
}

// --- Shift preview ---
const scheduleConfig = computed<ScheduleConfig>(() => ({
  eventName: name.value || 'Task',
  startDate: startDate.value?.toString() ?? '',
  endDate: endDate.value?.toString() ?? '',
  defaultStartTime: defaultStartTime.value,
  defaultEndTime: defaultEndTime.value,
  shiftDurationMinutes: shiftDurationMinutes.value,
  peoplePerShift: peoplePerShift.value,
  remainderMode: remainderMode.value,
  overrides: overrides.value,
}))

const {
  previewShifts,
  totalShifts,
  totalDays,
  shiftsByDate,
  hasRemainder,
  excludedShifts,
  toggleShiftExclusion,
  isShiftExcluded,
} = useShiftPreview(scheduleConfig)

const excludedShiftsChanged = computed(() => {
  const orig = originalExcludedShifts.value
  const curr = excludedShifts.value
  if (orig.size !== curr.size) return true
  for (const key of orig) {
    if (!curr.has(key)) return true
  }
  return false
})

const scheduleChanged = computed(() => {
  if (excludedShiftsChanged.value) return true
  if (!originalSchedule.value || !currentScheduleSnapshot.value) return true
  const orig = originalSchedule.value
  const curr = currentScheduleSnapshot.value
  return (
    orig.startDate !== curr.startDate ||
    orig.endDate !== curr.endDate ||
    orig.defaultStartTime !== curr.defaultStartTime ||
    orig.defaultEndTime !== curr.defaultEndTime ||
    orig.shiftDurationMinutes !== curr.shiftDurationMinutes ||
    orig.peoplePerShift !== curr.peoplePerShift ||
    orig.overrides !== curr.overrides
  )
})

const isValid = computed(() => {
  const hasName = isBatchMode.value || !!name.value.trim()
  if (!editsShifts.value) return hasName
  return (
    hasName &&
    !!startDate.value &&
    !!endDate.value &&
    !!defaultStartTime.value &&
    !!defaultEndTime.value &&
    shiftDurationMinutes.value >= 1 &&
    totalShifts.value > 0
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
  return eachDateInRange(startDate.value.toString(), endDate.value.toString()).filter(
    (dateStr) => !overrides.value.some((o) => o.date === dateStr),
  )
})

// --- Load task data ---
const loadTask = async () => {
  loading.value = true
  try {
    const response = await get<{ data: TaskRead }>({
      url: `/tasks/${eventId.value}`,
    })
    task.value = response.data
    const ev = response.data

    // Organisers and the task's people in charge. A batch is nothing but its
    // shifts, so it also needs the right to change those.
    if (!ev.can_manage || (isBatchMode.value && !ev.can_manage_shifts)) {
      router.replace({ name: 'task-detail', params: { eventId: eventId.value } })
      return
    }

    // How many batches there are decides what the task's own edit offers; in
    // batch mode the batch's config fills the form.
    try {
      const batchRes = await get<{ data: ShiftBatchRead[] }>({
        url: `/tasks/${eventId.value}/batches`,
      })
      batches.value = batchRes.data
    } catch {
      // Non-critical: the task-level config fills the form.
      batches.value = []
    }

    // Load parent event for default-window context (non-critical)
    if (ev.event_id) {
      try {
        const eventRes = await get<{ data: EventRead }>({ url: `/events/${ev.event_id}` })
        parentEvent.value = eventRes.data
      } catch {
        parentEvent.value = null
      }
    }

    // Populate form — use batch config if in batch mode
    name.value = ev.name
    description.value = ev.description ?? ''
    teamId.value = ev.team_id ?? null

    if (batchId.value) {
      batch.value = batches.value.find((b) => b.id === batchId.value) ?? null
    }

    const src = batch.value
    if (src) {
      location.value = src.location ?? ''
      locationId.value = src.location_id ?? null
      category.value = src.category ?? ''
      startDate.value = parseDate(src.start_date)
      endDate.value = parseDate(src.end_date)
      if (src.default_start_time) defaultStartTime.value = clockValue(src.default_start_time)
      if (src.default_end_time) defaultEndTime.value = clockValue(src.default_end_time)
      if (src.shift_duration_minutes) shiftDurationMinutes.value = src.shift_duration_minutes
      if (src.people_per_shift) peoplePerShift.value = src.people_per_shift
      if (src.remainder_mode) remainderMode.value = src.remainder_mode as RemainderMode
      if (src.schedule_overrides) {
        overrides.value = (
          src.schedule_overrides as Array<{ date: string; start_time: string; end_time: string }>
        ).map((o) => ({
          date: o.date,
          startTime: clockValue(o.start_time),
          endTime: clockValue(o.end_time),
        }))
      }
    } else {
      location.value = ev.location ?? ''
      locationId.value = ev.location_id ?? null
      category.value = ev.category ?? ''
      startDate.value = parseDate(ev.start_date)
      endDate.value = parseDate(ev.end_date)
      if (ev.default_start_time) defaultStartTime.value = clockValue(ev.default_start_time)
      if (ev.default_end_time) defaultEndTime.value = clockValue(ev.default_end_time)
      if (ev.shift_duration_minutes) shiftDurationMinutes.value = ev.shift_duration_minutes
      if (ev.people_per_shift) peoplePerShift.value = ev.people_per_shift
      if (ev.schedule_overrides) {
        overrides.value = (
          ev.schedule_overrides as Array<{ date: string; start_time: string; end_time: string }>
        ).map((o) => ({
          date: o.date,
          startTime: clockValue(o.start_time),
          endTime: clockValue(o.end_time),
        }))
      }
    }

    // Snapshot original schedule for change detection
    originalSchedule.value = {
      startDate: startDate.value!.toString(),
      endDate: endDate.value!.toString(),
      defaultStartTime: defaultStartTime.value,
      defaultEndTime: defaultEndTime.value,
      shiftDurationMinutes: shiftDurationMinutes.value,
      peoplePerShift: peoplePerShift.value,
      overrides: JSON.stringify(overrides.value),
    }

    // Fetch existing shifts with booking counts (scoped to batch if applicable)
    try {
      const shiftsRes = await get<{ data: { items: ShiftRead[] } }>({
        url: '/shifts/',
        query: { task_id: eventId.value, limit: 200 },
      })
      // Filter to batch shifts only when in batch mode
      const relevantShifts = batchId.value
        ? shiftsRes.data.items.filter((s: ShiftRead) => s.batch_id === batchId.value)
        : shiftsRes.data.items
      const bookingMap = new Map<string, number>()
      const existingKeys = new Set<string>()
      for (const shift of relevantShifts) {
        const st = clockValue(shift.start_time)
        const et = clockValue(shift.end_time)
        const key = `${shift.date}|${st}|${et}`
        existingKeys.add(key)
        if ((shift.current_bookings ?? 0) > 0) {
          bookingMap.set(key, shift.current_bookings!)
        }
      }
      existingBookings.value = bookingMap

      // Pre-exclude preview shifts that were manually deleted from the backend
      const toExclude = new Set<string>()
      for (const previewShift of previewShifts.value) {
        const key = slotKey(previewShift)
        if (!existingKeys.has(key)) {
          toExclude.add(key)
        }
      }
      if (toExclude.size > 0) {
        excludedShifts.value = new Set(toExclude)
      }
      // Snapshot the initial excluded state for change detection
      originalExcludedShifts.value = new Set(excludedShifts.value)
    } catch {
      // Non-critical — preview just won't show booking counts
    }

    // Set breadcrumbs
    breadcrumbStore.setBreadcrumbs([
      { title: 'Tasks', titleKey: 'duties.tasks.title', to: { name: 'tasks' } },
      { title: ev.name, to: { name: 'task-detail', params: { eventId: ev.id } } },
      {
        title: isBatchMode.value
          ? t('duties.tasks.editView.editBatch')
          : t('duties.tasks.editView.title'),
      },
    ])
  } catch (error) {
    toastApiError(error)
    router.push({ name: 'tasks' })
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
    // Always together: text without the id would unlink the location.
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
    },
  }
}

// --- Submit ---
const handleSubmit = async () => {
  if (!isValid.value || submitting.value) return
  submitting.value = true

  try {
    // The team is a task setting that shift regeneration does not carry, so
    // it is saved on its own whichever path follows.
    if (!isBatchMode.value && teamId.value !== (task.value?.team_id ?? null)) {
      await patch({ url: `/tasks/${eventId.value}`, body: { team_id: teamId.value } })
    }
    if (!isBatchMode.value && (!scheduleChanged.value || !editsShifts.value)) {
      // Only details changed — simple PATCH, no shift regeneration
      await patch<{ data: TaskRead }>({
        url: `/tasks/${eventId.value}`,
        body: {
          name: name.value,
          description: description.value || null,
          location_id: locationId.value,
          location: location.value || null,
          category: category.value || null,
        },
      })
      toast.success(t('duties.tasks.editView.saveSuccess'))
      router.push({ name: 'task-detail', params: { eventId: eventId.value } })
      return
    }

    // Schedule changed — dry run first to check for affected bookings
    const regenQuery: Record<string, unknown> = { dry_run: true }
    if (batchId.value) regenQuery.batch_id = batchId.value

    const preview = await post<{ data: ShiftRegenerationResult }>({
      url: `/tasks/${eventId.value}/regenerate-shifts`,
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

    await post<{ data: ShiftRegenerationResult }>({
      url: `/tasks/${eventId.value}/regenerate-shifts`,
      query: regenQuery,
      body: buildPayload(),
    })

    toast.success(t('duties.tasks.editView.saveSuccess'))
    router.push({ name: 'task-detail', params: { eventId: eventId.value } })
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
          {{
            isBatchMode ? t('duties.tasks.editView.editBatch') : t('duties.tasks.editView.title')
          }}
        </h1>
        <p class="text-muted-foreground">
          {{
            isBatchMode
              ? t('duties.tasks.editView.editBatchSubtitle')
              : editsShifts
                ? t('duties.tasks.editView.subtitle')
                : t('duties.tasks.editView.subtitleDetails')
          }}
        </p>
        <p
          v-if="!canManageShifts"
          class="flex gap-2 text-sm text-muted-foreground"
          data-testid="task-voucher-shifts-locked"
        >
          <Info class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          {{ t('duties.tasks.managers.voucherShiftsLocked') }}
        </p>
        <p
          v-else-if="!editsShifts"
          class="flex gap-2 text-sm text-muted-foreground"
          data-testid="task-shifts-in-batches"
        >
          <Info class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          {{ t('duties.tasks.editView.batchesNote', { count: batches.length }) }}
        </p>
      </div>

      <!-- Task Details (hidden in batch mode) -->
      <Card v-if="!isBatchMode">
        <CardHeader>
          <CardTitle>{{ t('duties.tasks.createView.sections.details') }}</CardTitle>
          <CardDescription>{{ t('duties.tasks.createView.sections.detailsDesc') }}</CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="space-y-2">
            <Label for="task-name">{{ t('duties.tasks.fields.name') }} *</Label>
            <Input id="task-name" v-model="name" data-testid="input-task-name" />
          </div>
          <div class="space-y-2">
            <Label for="task-description">{{ t('duties.tasks.fields.description') }}</Label>
            <Textarea id="task-description" v-model="description" :rows="3" class="max-h-[150px]" />
          </div>
          <div class="grid items-start gap-4 sm:grid-cols-2">
            <div class="space-y-2">
              <Label for="task-location">{{ t('duties.tasks.fields.location') }}</Label>
              <LocationPicker
                v-model:location-id="locationId"
                v-model:text="location"
                :event-id="task?.event_id"
                input-id="task-location"
              />
            </div>
            <div class="space-y-2">
              <Label for="task-category">{{ t('duties.tasks.fields.category') }}</Label>
              <Input id="task-category" v-model="category" />
            </div>
          </div>
          <!--
            With several series the task's place and category are what the task
            list, its quick view and the printout show; each series' shifts keep
            their own, which the series' Edit changes.
          -->
          <p
            v-if="severalBatches"
            class="text-sm text-muted-foreground"
            data-testid="task-place-in-list"
          >
            {{ t('duties.tasks.editView.placeInListNote') }}
          </p>
        </CardContent>
      </Card>

      <!-- Who can book (hidden in batch mode: a team is set on the task) -->
      <Card v-if="!isBatchMode && canAdminEvent" data-testid="section-who-can-book">
        <CardHeader>
          <CardTitle>{{ t('teamLocks.picker.title') }}</CardTitle>
          <CardDescription>{{ t('teamLocks.picker.subtitle') }}</CardDescription>
        </CardHeader>
        <CardContent>
          <TeamPicker v-model="teamId" :event-id="task?.event_id" input-id="task-team" />
        </CardContent>
      </Card>

      <!-- Batch Details (only in batch mode) -->
      <Card v-if="isBatchMode">
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
              <Label for="batch-category">{{ t('duties.tasks.fields.category') }}</Label>
              <Input id="batch-category" v-model="category" />
            </div>
          </div>
        </CardContent>
      </Card>

      <!-- Task Dates: they bound the shifts, so they go with the schedule -->
      <Card v-if="editsShifts">
        <CardHeader>
          <CardTitle>{{ t('duties.tasks.createView.sections.dates') }}</CardTitle>
          <CardDescription>{{ t('duties.tasks.createView.sections.datesDesc') }}</CardDescription>
        </CardHeader>
        <CardContent>
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <Label>{{ t('duties.tasks.fields.startDate') }} *</Label>
              <DatePicker v-model="startDate" :max-value="endDate" />
            </div>
            <div class="space-y-2">
              <Label>{{ t('duties.tasks.fields.endDate') }} *</Label>
              <DatePicker v-model="endDate" :min-value="startDate" :highlight="startDate" />
            </div>
          </div>
        </CardContent>
      </Card>

      <!-- Schedule & Shifts -->
      <Card v-if="editsShifts" data-testid="section-schedule">
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
            :event-start-time="parentEvent?.default_start_time ?? null"
            :event-end-time="parentEvent?.default_end_time ?? null"
            show-overrides
          />
        </CardContent>
      </Card>

      <!-- Preview: leaving a shift out here removes it -->
      <Card v-if="editsShifts">
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
              :get-booking-count="getShiftBookingCount"
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
          <RefreshCw v-if="scheduleChanged && editsShifts" class="mr-2 h-4 w-4" />
          {{
            submitting
              ? t('duties.tasks.editView.saving')
              : scheduleChanged && editsShifts
                ? t('duties.tasks.editView.regenerate')
                : t('common.actions.save')
          }}
        </Button>
      </div>
    </template>

    <!-- Affected Bookings Dialog -->
    <ResponsiveDialog v-model:open="showAffectedDialog">
      <ResponsiveDialogContent dialog-class="sm:max-w-lg">
        <ResponsiveDialogHeader>
          <ResponsiveDialogTitle class="flex items-center gap-2">
            <Info class="h-5 w-5 text-destructive" />
            {{ t('duties.tasks.editView.affectedBookings.title') }}
          </ResponsiveDialogTitle>
          <ResponsiveDialogDescription>
            {{
              previewHasLocked
                ? t('duties.tasks.editView.affectedBookings.descriptionLocked')
                : t('duties.tasks.editView.affectedBookings.description')
            }}
          </ResponsiveDialogDescription>
        </ResponsiveDialogHeader>

        <ResponsiveDialogBody v-if="pendingPreview" class="space-y-3 pb-2">
          <!-- Summary badges -->
          <div class="flex gap-2 flex-wrap">
            <Badge variant="default">
              {{ t('duties.tasks.editView.preview.added', { count: pendingPreview.shifts_added }) }}
            </Badge>
            <Badge variant="destructive">
              {{
                t('duties.tasks.editView.preview.removed', { count: pendingPreview.shifts_removed })
              }}
            </Badge>
            <Badge variant="secondary">
              {{ t('duties.tasks.editView.preview.kept', { count: pendingPreview.shifts_kept }) }}
            </Badge>
          </div>

          <!-- Affected bookings list -->
          <div class="max-h-60 space-y-2 overflow-y-auto rounded-md border p-3">
            <div
              v-for="booking in pendingPreview.affected_bookings"
              :key="booking.booking_id"
              class="rounded-md bg-muted/50 px-3 py-2 text-sm"
              :data-testid="`affected-booking-${booking.booking_id}`"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="min-w-0">
                  <p class="font-medium">{{ booking.slot_title }}</p>
                  <p class="text-muted-foreground">
                    {{ formatDateLabel(booking.slot_date) }}
                    <template v-if="booking.slot_start_time">
                      {{ formatTime(booking.slot_start_time) }} -
                      {{ formatTime(booking.slot_end_time) }}
                    </template>
                  </p>
                </div>
                <Badge variant="outline" class="max-w-[50%] shrink-0 text-xs">
                  <span class="truncate">{{ booking.user_name || '?' }}</span>
                </Badge>
              </div>
              <p
                v-if="booking.locked"
                class="mt-1.5 flex items-start gap-1.5 text-xs text-destructive"
                data-testid="affected-booking-locked"
              >
                <Lock class="mt-0.5 h-3 w-3 shrink-0" />
                {{ t('duties.tasks.editView.affectedBookings.locked') }}
              </p>
            </div>
          </div>

          <!-- Why "Proceed anyway" is greyed out, and what to do instead -->
          <p
            v-if="previewHasLocked"
            class="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm"
            data-testid="affected-bookings-locked-hint"
          >
            <Lock class="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            {{ t('duties.tasks.editView.affectedBookings.lockedHint') }}
          </p>
        </ResponsiveDialogBody>

        <ResponsiveDialogFooter>
          <Button variant="outline" @click="showAffectedDialog = false">
            {{ t('duties.tasks.editView.affectedBookings.cancel') }}
          </Button>
          <Button
            variant="destructive"
            :disabled="previewHasLocked"
            data-testid="btn-confirm-regeneration"
            @click="confirmRegeneration"
          >
            {{ t('duties.tasks.editView.affectedBookings.confirm') }}
          </Button>
        </ResponsiveDialogFooter>
      </ResponsiveDialogContent>
    </ResponsiveDialog>
  </div>
</template>
