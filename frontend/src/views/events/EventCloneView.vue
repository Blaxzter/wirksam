<script setup lang="ts">
import { computed, nextTick, onMounted, ref, shallowRef, watch } from 'vue'

import type { DateValue } from '@internationalized/date'
import { parseDate } from '@internationalized/date'
import {
  ArrowLeft,
  CalendarDays,
  Check,
  ChevronDown,
  ClipboardList,
  Copy,
  Megaphone,
  TriangleAlert,
  Users,
} from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useFormatters } from '@/composables/useFormatters'
import { type PreviewShift, eachDateInRange } from '@/composables/useShiftPreview'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
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
import {
  Stepper,
  StepperIndicator,
  StepperItem,
  StepperSeparator,
  StepperTitle,
  StepperTrigger,
} from '@/components/ui/stepper'
import { Switch } from '@/components/ui/switch'
import Textarea from '@/components/ui/textarea/Textarea.vue'
import { TimePicker } from '@/components/ui/time-picker'

import ShiftPreviewGrid from '@/components/tasks/ShiftPreviewGrid.vue'

import type {
  EventCloneRequest,
  EventCloneResponse,
  EventCloneTask,
  EventRead,
  ShiftBatchRead,
  ShiftListResponse,
  ShiftRead,
  TaskListResponse,
  TaskRead,
} from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const { t, locale } = useI18n()
const { formatTimeRange } = useFormatters()
const route = useRoute()
const router = useRouter()
const { get, post } = useAuthenticatedClient()
const authStore = useAuthStore()

const sourceId = route.params.sourceId as string

/** 52 weeks: "the same weekend next year", with the weekday left alone. */
const DEFAULT_OFFSET_DAYS = 364
const NOTE_MAX_LENGTH = 500
/** The API refuses more than this in one request — every batch and every shift
 *  row of every task named here is written in a single transaction. */
const MAX_TASKS = 50
const DURATION_OPTIONS = [15, 30, 45, 60, 90, 120]
/** `GET /shifts/` caps `limit` at 200 and 422s above it, so the preload pages. */
const SHIFT_PAGE_SIZE = 200
/** A stop so a server that never advances cannot spin here forever. */
const MAX_SHIFT_PAGES = 25

// --- Calendar arithmetic ------------------------------------------------
// Everything is an ISO 'YYYY-MM-DD' string held at UTC midnight, the same way
// useShiftPreview does it: a local-midnight Date slides a day either side of
// Greenwich and drifts on the nights the clocks change.

const DAY_MS = 86_400_000

function toUtcMs(iso: string): number {
  return new Date(`${iso}T00:00:00Z`).getTime()
}

function addDays(iso: string, days: number): string {
  const d = new Date(toUtcMs(iso))
  if (Number.isNaN(d.getTime())) return iso
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

function daysBetween(fromIso: string, toIso: string): number {
  return Math.round((toUtcMs(toIso) - toUtcMs(fromIso)) / DAY_MS)
}

/**
 * The one shape the API's `dt.time` accepts, spelled out.
 *
 * TimePicker's editor is a plain text input that emits whatever is typed, so
 * '9:30' reaches us intact; `dt.time` rejects the single-digit hour with a
 * body-level 422 the user cannot act on. Both the validator and the request
 * builder go through here.
 */
const CLOCK_RE = /^([01]\d|2[0-3]):([0-5]\d)$/

function isClock(value: string): boolean {
  return CLOCK_RE.test(value)
}

/** '9:30' → '09:30'. Defensive: the validator already refuses the former. */
function padClock(value: string): string {
  const [h = '', m = ''] = value.split(':')
  return `${h.padStart(2, '0')}:${m.padStart(2, '0')}`
}

function timeToMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':')
  const hi = Number.parseInt(h, 10)
  const mi = Number.parseInt(m, 10)
  if (Number.isNaN(hi) || Number.isNaN(mi)) return Number.NaN
  return hi * 60 + mi
}

function minutesToTime(total: number): string {
  const h = Math.floor(total / 60)
    .toString()
    .padStart(2, '0')
  const m = (total % 60).toString().padStart(2, '0')
  return `${h}:${m}`
}

/** 'HH:MM:SS' (what the API speaks) → 'HH:MM' (what TimePicker speaks). */
function toClock(value: string | null | undefined, fallback: string): string {
  return value ? value.slice(0, 5) : fallback
}

// --- Date labels --------------------------------------------------------
// `toLocaleDateString` builds a fresh Intl formatter per call, and this screen
// prints a date label several times per task on every render. One formatter per
// locale, plus a cache keyed by the ISO string, keeps it off the render path.

const dateLabelFormat = computed(
  () => new Intl.DateTimeFormat(locale.value, { weekday: 'short', month: 'short', day: 'numeric' }),
)
const dateLabelCache = new Map<string, string>()

watch(dateLabelFormat, () => dateLabelCache.clear())

function dateLabel(iso: string): string {
  if (!iso) return ''
  const cached = dateLabelCache.get(iso)
  if (cached !== undefined) return cached
  const d = new Date(`${iso}T00:00:00`)
  const label = Number.isNaN(d.getTime()) ? iso : dateLabelFormat.value.format(d)
  dateLabelCache.set(iso, label)
  return label
}

// --- Loaded source ------------------------------------------------------

const loading = ref(true)
const sourceEvent = ref<EventRead | null>(null)
const sourceTasks = ref<TaskRead[]>([])
const shiftsByTask = ref<Map<string, ShiftRead[]>>(new Map())
/**
 * The source task's shift blocks.
 *
 * `_assert_rows_fit_event` rejects on batch range *before* it looks at a single
 * shift, and a block may legitimately run wider than the shift rows inside it —
 * so previewing the shifts alone cannot predict that 422.
 */
const batchesByTask = ref<Map<string, ShiftBatchRead[]>>(new Map())
/**
 * Tasks whose shifts could not be read.
 *
 * An empty list and an unreadable list look identical downstream, and the
 * backend copies every source shift either way — so the difference has to be
 * carried explicitly rather than reported as a confident zero.
 */
const shiftsUnavailable = ref<Set<string>>(new Set())
/**
 * Tasks whose shifts or blocks could not be read, so no date check could run.
 *
 * Separate from `shiftsUnavailable`: a failed *block* fetch leaves the shift
 * counts intact but still takes the check with it, and a check that quietly
 * passed on nothing reads as "these dates are fine".
 */
const rangeCheckUnavailable = ref<Set<string>>(new Set())
/** Bumped when the shift preload finishes, so the preview memo invalidates. */
const shiftsVersion = ref(0)

const sourceDurationDays = computed(() => {
  const ev = sourceEvent.value
  if (!ev) return 0
  return Math.max(0, daysBetween(ev.start_date, ev.end_date))
})

// --- Section (a): when --------------------------------------------------

const name = ref('')
// shallowRef, not ref: Vue's deep unwrap strips the class identity off a
// CalendarDate and `.compare()` stops working on it.
const startDate = shallowRef<DateValue>()
const endDate = shallowRef<DateValue>()
/** Once the end date is edited by hand, a new start date stops moving it. */
const endDateTouched = ref(false)

const newStartIso = computed(() => startDate.value?.toString() ?? '')
const newEndIso = computed(() => endDate.value?.toString() ?? '')

const offsetDays = computed(() => {
  if (!sourceEvent.value || !newStartIso.value) return null
  return daysBetween(sourceEvent.value.start_date, newStartIso.value)
})

const keepsWeekday = computed(() => {
  const offset = offsetDays.value
  return offset !== null && offset !== 0 && offset % 7 === 0
})

const newDayCount = computed(() => {
  if (!newStartIso.value || !newEndIso.value) return null
  const days = daysBetween(newStartIso.value, newEndIso.value)
  return days < 0 ? null : days + 1
})

// Deriving the end date is a watcher, so it also covers the prefill — which is
// why the prefill waits a tick before writing an end date of its own.
watch(startDate, () => {
  if (endDateTouched.value || !newStartIso.value) return
  endDate.value = parseDate(addDays(newStartIso.value, sourceDurationDays.value))
})

// --- Section (b): tasks -------------------------------------------------

const selectedTaskIds = ref<Set<string>>(new Set())
const copyMembers = ref(true)

const selectedTasks = computed(() =>
  sourceTasks.value.filter((task) => selectedTaskIds.value.has(task.id)),
)

/** The tasks "Pick every task" reaches: the request refuses more than MAX_TASKS. */
const selectableTaskIds = computed(() => sourceTasks.value.slice(0, MAX_TASKS).map((t) => t.id))

const allTasksSelected = computed(
  () =>
    selectableTaskIds.value.length > 0 &&
    selectableTaskIds.value.every((id) => selectedTaskIds.value.has(id)),
)

const selectAllState = computed<boolean | 'indeterminate'>(() => {
  if (selectedTaskIds.value.size === 0) return false
  return allTasksSelected.value ? true : 'indeterminate'
})

function toggleTask(taskId: string, checked: boolean | 'indeterminate') {
  const next = new Set(selectedTaskIds.value)
  if (checked === true) next.add(taskId)
  else next.delete(taskId)
  selectedTaskIds.value = next
}

// Capped at the limit: selecting every task on a 60-task event used to produce
// a state no control on the page could undo.
function toggleAllTasks(checked: boolean | 'indeterminate') {
  selectedTaskIds.value = checked === true ? new Set(selectableTaskIds.value) : new Set()
}

// --- Section (c): adjust ------------------------------------------------

interface TaskConfig {
  mode: 'copy' | 'regenerate'
  /**
   * What the copied task starts as.
   *
   * Visibility is gated on the *task's* status, never on the event's, and
   * publishing an event does not cascade to its tasks — so this is the only
   * setting that decides whether anyone can book the copy.
   */
  status: 'draft' | 'published'
  name: string
  location: string
  /** ISO strings, never DateValue: an array of DateValue loses class identity. */
  startDate: string
  endDate: string
  datesTouched: boolean
  startTime: string
  endTime: string
  durationMinutes: number
  peoplePerShift: number
  expanded: boolean
}

const taskConfigs = ref<Record<string, TaskConfig>>({})

/** Selected tasks whose config exists — everything per-task iterates this. */
const configuredTasks = computed(() =>
  selectedTasks.value.filter((task) => taskConfigs.value[task.id] !== undefined),
)

function buildTaskConfig(task: TaskRead, offset: number): TaskConfig {
  return {
    mode: 'copy',
    // Hidden until the organiser says otherwise: a copied roster landing on a
    // bookable task nobody has reviewed is the worse of the two mistakes.
    status: 'draft',
    name: task.name,
    location: task.location ?? '',
    startDate: addDays(task.start_date, offset),
    endDate: addDays(task.end_date, offset),
    datesTouched: false,
    startTime: toClock(task.default_start_time, '10:00'),
    endTime: toClock(task.default_end_time, '18:00'),
    durationMinutes: task.shift_duration_minutes ?? 60,
    peoplePerShift: task.people_per_shift ?? 1,
    expanded: false,
  }
}

// Moving the event moves every task that has not been re-dated by hand.
watch(offsetDays, (offset) => {
  if (offset === null) return
  for (const task of sourceTasks.value) {
    const cfg = taskConfigs.value[task.id]
    if (!cfg || cfg.datesTouched) continue
    cfg.startDate = addDays(task.start_date, offset)
    cfg.endDate = addDays(task.end_date, offset)
  }
})

function setTaskDate(taskId: string, field: 'startDate' | 'endDate', value: DateValue | undefined) {
  const cfg = taskConfigs.value[taskId]
  if (!cfg || !value) return
  cfg[field] = value.toString()
  cfg.datesTouched = true
}

function taskDateValue(iso: string): DateValue | undefined {
  return iso ? parseDate(iso) : undefined
}

/**
 * The shift lengths this task's dropdown offers.
 *
 * A source task set to 3-hour shifts is not in DURATION_OPTIONS, and reka-ui
 * derives the trigger label from a matching SelectItem — with no match the box
 * renders empty while the preview still uses the real number.
 */
function durationOptions(taskId: string): number[] {
  const current = taskConfigs.value[taskId]?.durationMinutes
  const options = new Set(DURATION_OPTIONS)
  if (current && current > 0) options.add(current)
  return [...options].sort((a, b) => a - b)
}

/** Copy mode reproduces shift rows verbatim, so a rename stops at the task. */
function copyKeepsOldLabels(task: TaskRead): boolean {
  const cfg = taskConfigs.value[task.id]
  if (!cfg || cfg.mode !== 'copy') return false
  return cfg.name.trim() !== task.name || cfg.location.trim() !== (task.location ?? '')
}

// --- Shift preview ------------------------------------------------------

/**
 * The shifts one day of a regenerated task would get.
 *
 * Mirrors the backend generator's `drop` remainder handling: the loop only
 * emits while a whole shift still fits. `remainder_mode` lives on the source
 * batch and nothing in this request can change it, so a source built with
 * "short" or "extend" ends one shift a day short of this count — which is
 * itself a reason the wizard defaults to copying.
 */
function generateDay(
  label: string,
  date: string,
  dayStart: string,
  dayEnd: string,
  durationMinutes: number,
): PreviewShift[] {
  const start = timeToMinutes(dayStart)
  const end = timeToMinutes(dayEnd)
  if (Number.isNaN(start) || Number.isNaN(end) || durationMinutes < 1) return []

  const shifts: PreviewShift[] = []
  let cursor = start
  while (cursor + durationMinutes <= end) {
    const startTime = minutesToTime(cursor)
    const endTime = minutesToTime(cursor + durationMinutes)
    shifts.push({ date, startTime, endTime, title: `${label} ${startTime}-${endTime}` })
    cursor += durationMinutes
  }
  return shifts
}

interface TaskPreview {
  shifts: PreviewShift[]
  spots: number
  /** Earliest and latest previewed shift date, '' when there are none. */
  minDate: string
  maxDate: string
}

function withBounds(shifts: PreviewShift[], spots: number): TaskPreview {
  let minDate = ''
  let maxDate = ''
  for (const shift of shifts) {
    if (!minDate || shift.date < minDate) minDate = shift.date
    if (!maxDate || shift.date > maxDate) maxDate = shift.date
  }
  return { shifts, spots, minDate, maxDate }
}

function previewForTask(task: TaskRead, cfg: TaskConfig): TaskPreview {
  const taskOffset = daysBetween(task.start_date, cfg.startDate)

  if (cfg.mode === 'copy') {
    const existing = shiftsByTask.value.get(task.id) ?? []
    return withBounds(
      existing.map((shift) => ({
        date: addDays(shift.date, taskOffset),
        startTime: toClock(shift.start_time, ''),
        endTime: toClock(shift.end_time, ''),
        title: shift.title,
      })),
      existing.reduce((sum, shift) => sum + (shift.max_bookings ?? 1), 0),
    )
  }

  // Per-date exceptions travel with the task, so they move by the task's own
  // offset. They are read off the task row because that is what the API hands
  // back; the batch carries the same list.
  const overrides = new Map<string, { start: string; end: string }>()
  for (const entry of task.schedule_overrides ?? []) {
    const date = entry.date
    const start = entry.start_time
    const end = entry.end_time
    if (typeof date !== 'string' || typeof start !== 'string' || typeof end !== 'string') continue
    overrides.set(addDays(date, taskOffset), { start: start.slice(0, 5), end: end.slice(0, 5) })
  }

  const shifts: PreviewShift[] = []
  for (const date of eachDateInRange(cfg.startDate, cfg.endDate)) {
    const override = overrides.get(date)
    shifts.push(
      ...generateDay(
        cfg.name || task.name,
        date,
        override?.start ?? cfg.startTime,
        override?.end ?? cfg.endTime,
        cfg.durationMinutes,
      ),
    )
  }
  return withBounds(shifts, shifts.length * Math.max(1, cfg.peoplePerShift))
}

/**
 * Everything `previewForTask` reads, as one string.
 *
 * One computed covers every selected task, so any keystroke anywhere re-runs
 * it. Regenerating all fifty previews on each of those runs is what made the
 * inputs drop characters; the signature keeps the work to the task that
 * actually changed, and hands every other task back the object it already had
 * — which is also what keeps ShiftPreviewGrid's prop identity stable.
 */
function previewKey(task: TaskRead, cfg: TaskConfig): string {
  return [
    shiftsVersion.value,
    cfg.mode,
    cfg.name,
    cfg.startDate,
    cfg.endDate,
    cfg.startTime,
    cfg.endTime,
    cfg.durationMinutes,
    cfg.peoplePerShift,
    task.start_date,
  ].join('|')
}

const previewCache = new Map<string, { key: string; value: TaskPreview }>()

const previews = computed<Map<string, TaskPreview>>(() => {
  const out = new Map<string, TaskPreview>()
  for (const task of selectedTasks.value) {
    const cfg = taskConfigs.value[task.id]
    if (!cfg) continue
    const key = previewKey(task, cfg)
    const cached = previewCache.get(task.id)
    if (cached && cached.key === key) {
      out.set(task.id, cached.value)
      continue
    }
    const value = previewForTask(task, cfg)
    previewCache.set(task.id, { key, value })
    out.set(task.id, value)
  }
  return out
})

function shiftCountFor(taskId: string): number {
  return previews.value.get(taskId)?.shifts.length ?? 0
}

/**
 * Whether a count can be shown at all.
 *
 * In copy mode the number comes from the fetched shift list. When that fetch
 * failed there is no number — and printing 0 would be a lie the backend
 * immediately contradicts.
 */
function countUnknownFor(taskId: string): boolean {
  return shiftsUnavailable.value.has(taskId) && taskConfigs.value[taskId]?.mode === 'copy'
}

const totalsIncomplete = computed(() =>
  configuredTasks.value.some((task) => countUnknownFor(task.id)),
)

// Keyed by the preview object, so the grid keeps the same Map instance for as
// long as the preview behind it is unchanged.
const groupedCache = new WeakMap<TaskPreview, Map<string, PreviewShift[]>>()

function shiftsByDateFor(taskId: string): Map<string, PreviewShift[]> {
  const preview = previews.value.get(taskId)
  if (!preview) return new Map()
  const cached = groupedCache.get(preview)
  if (cached) return cached
  const grouped = new Map<string, PreviewShift[]>()
  for (const shift of preview.shifts) {
    const existing = grouped.get(shift.date) ?? []
    existing.push(shift)
    grouped.set(shift.date, existing)
  }
  groupedCache.set(preview, grouped)
  return grouped
}

/** ShiftPreviewGrid is read-only here — nothing in a clone can be struck out. */
const neverExcluded = () => false

/** How many shifts the source task holds today, before anything is changed. */
function sourceShiftCount(taskId: string): number {
  return (shiftsByTask.value.get(taskId) ?? []).length
}

const totalShifts = computed(() =>
  configuredTasks.value.reduce((sum, task) => sum + shiftCountFor(task.id), 0),
)

const totalSpots = computed(() =>
  configuredTasks.value.reduce((sum, task) => sum + (previews.value.get(task.id)?.spots ?? 0), 0),
)

const draftTaskCount = computed(
  () =>
    configuredTasks.value.filter((task) => taskConfigs.value[task.id]?.status === 'draft').length,
)

/**
 * What Review says about booking, matched to what was actually chosen.
 *
 * Publishing the event does not publish its tasks, so "publish it when you are
 * ready" is only true of the event itself — when every task is a draft the copy
 * stays unbookable until each one is published from the task list.
 */
const taskStatusNote = computed(() => {
  const total = configuredTasks.value.length
  if (total === 0) return ''
  const drafts = draftTaskCount.value
  if (drafts === total) return t('duties.events.clone.review.taskStatusAllDraft')
  if (drafts === 0) return t('duties.events.clone.review.taskStatusAllOpen')
  return t('duties.events.clone.review.taskStatusMixed', { draft: drafts, total })
})

// --- Section (d): announce ---------------------------------------------

const announceSend = ref(false)
const announceNote = ref('')

const memberCount = computed(() => sourceEvent.value?.member_count ?? 0)

/**
 * Whoever is cloning is never copied and never written to — they are already
 * looking at the result. `eventRoles` is the raw membership map, unlike
 * `eventRole()`, which answers 'owner' for a superadmin who is not in the
 * event at all and would make this subtract a row that does not exist.
 */
const clonerIsMember = computed(() => Boolean(authStore.eventRoles[sourceId]))

const otherMemberCount = computed(() =>
  Math.max(0, memberCount.value - (clonerIsMember.value ? 1 : 0)),
)

const audienceCount = computed(() => (copyMembers.value ? otherMemberCount.value : 0))

const canAnnounce = computed(() => copyMembers.value && audienceCount.value > 0)

const willNotify = computed(() => canAnnounce.value && announceSend.value)

const noteTooLong = computed(() => announceNote.value.length > NOTE_MAX_LENGTH)

// Turning the roster off takes the audience with it, so the switch must not
// stay armed underneath a section that says nobody will hear about this.
watch(canAnnounce, (value) => {
  if (!value) announceSend.value = false
})

// --- Wizard plumbing ----------------------------------------------------

const submitting = ref(false)

const sections = ['when', 'tasks', 'adjust', 'announce', 'review'] as const

type SectionName = (typeof sections)[number]

const activeSection = ref<SectionName>('when')

/** The steps that have actually been opened — the only ones a tick may claim. */
const visitedSections = ref<Set<SectionName>>(new Set<SectionName>(['when']))

/** One icon per step, worn by the step card's heading. */
const stepIcons = {
  when: CalendarDays,
  tasks: ClipboardList,
  adjust: Copy,
  announce: Megaphone,
  review: Copy,
}

const isWhenValid = computed(() => {
  if (!name.value.trim() || !newStartIso.value || !newEndIso.value) return false
  return daysBetween(newStartIso.value, newEndIso.value) >= 0
})

const isTasksValid = computed(() => selectedTasks.value.length <= MAX_TASKS)

/**
 * The first shifted block edge that falls outside the new event, or ''.
 *
 * Blocks follow the task, not the event — `_clone_batch` shifts them by the
 * task's own delta — so the offset here is the task's, exactly as the backend
 * computes it.
 */
function strayBatchDate(task: TaskRead, cfg: TaskConfig): string {
  if (!newStartIso.value || !newEndIso.value) return ''
  const taskOffset = daysBetween(task.start_date, cfg.startDate)
  for (const batch of batchesByTask.value.get(task.id) ?? []) {
    const start = addDays(batch.start_date, taskOffset)
    if (daysBetween(newStartIso.value, start) < 0) return start
    const end = addDays(batch.end_date, taskOffset)
    if (daysBetween(end, newEndIso.value) < 0) return end
  }
  return ''
}

const taskProblems = computed<Record<string, string>>(() => {
  const problems: Record<string, string> = {}
  for (const task of configuredTasks.value) {
    const cfg = taskConfigs.value[task.id]
    if (!cfg) continue
    if (!cfg.name.trim()) {
      problems[task.id] = t('duties.events.clone.adjust.errors.name')
      continue
    }
    if (daysBetween(cfg.startDate, cfg.endDate) < 0) {
      problems[task.id] = t('duties.events.clone.adjust.errors.order')
      continue
    }
    if (
      newStartIso.value &&
      newEndIso.value &&
      (daysBetween(newStartIso.value, cfg.startDate) < 0 ||
        daysBetween(cfg.endDate, newEndIso.value) < 0)
    ) {
      problems[task.id] = t('duties.events.clone.adjust.errors.outside')
      continue
    }
    if (cfg.mode === 'regenerate') {
      if (!isClock(cfg.startTime) || !isClock(cfg.endTime)) {
        problems[task.id] = t('duties.events.clone.adjust.errors.timeFormat')
        continue
      }
      if (timeToMinutes(cfg.endTime) <= timeToMinutes(cfg.startTime)) {
        problems[task.id] = t('duties.events.clone.adjust.errors.times')
        continue
      }
      if (cfg.durationMinutes < 1 || cfg.peoplePerShift < 1) {
        problems[task.id] = t('duties.events.clone.adjust.errors.numbers')
        continue
      }
    }
    // The backend checks every cloned batch and every cloned shift against the
    // new window, not just the task header — a source task may legitimately own
    // a shift outside its own dates. Catching it here names the date instead of
    // trading it for a 422 that names nothing.
    //
    // Blocks first, because that is the order `_assert_rows_fit_event` uses and
    // because a block can run wider than the shifts inside it, so the shift
    // preview below would let it through.
    const strayBatch = strayBatchDate(task, cfg)
    if (strayBatch) {
      problems[task.id] = t('duties.events.clone.adjust.errors.batchOutside', {
        date: dateLabel(strayBatch),
      })
      continue
    }
    const preview = previews.value.get(task.id)
    if (!preview || !newStartIso.value || !newEndIso.value) continue
    const stray =
      preview.minDate && daysBetween(newStartIso.value, preview.minDate) < 0
        ? preview.minDate
        : preview.maxDate && daysBetween(preview.maxDate, newEndIso.value) < 0
          ? preview.maxDate
          : ''
    if (stray) {
      problems[task.id] = t('duties.events.clone.adjust.errors.shiftOutside', {
        date: dateLabel(stray),
      })
    }
  }
  return problems
})

const hasTaskProblems = computed(() => Object.keys(taskProblems.value).length > 0)

const isAdjustValid = computed(() => !hasTaskProblems.value)

const isAnnounceValid = computed(() => !noteTooLong.value)

const sectionValid: Record<string, () => boolean> = {
  when: () => isWhenValid.value,
  tasks: () => isTasksValid.value,
  adjust: () => isAdjustValid.value,
  announce: () => isAnnounceValid.value,
}

const isCurrentSectionValid = computed(() => {
  const check = sectionValid[activeSection.value]
  return check ? check() : true
})

/**
 * Whether the card header carries the count chip.
 *
 * It also switches the header to two columns: CardAction is placed into the
 * second one explicitly, and without a second column to place it in it would
 * push the description out of the title's row.
 */
const showSelectedCount = computed(
  () => activeSection.value === 'tasks' && selectedTasks.value.length > 0,
)

/** How many of the chosen tasks are currently wrong. */
const problemTaskCount = computed(() => Object.keys(taskProblems.value).length)

/** The first broken task, named along with what is wrong with it. */
const firstTaskProblem = computed(() => {
  for (const task of configuredTasks.value) {
    const problem = taskProblems.value[task.id]
    if (!problem) continue
    return t('duties.events.clone.review.problemItem', {
      task: taskConfigs.value[task.id]?.name.trim() || task.name,
      problem,
    })
  }
  return ''
})

/**
 * Why the forward button is dead, on the step that is actually holding things
 * up — which is always the one on screen.
 *
 * Every forward move gates on the departing step being valid, so a later step
 * can never be entered with a problem behind it and a list of everything wrong
 * would have nowhere to render. The reason has to travel with the step instead,
 * or a greyed-out Next explains nothing at all.
 */
const stepBlockedReason = computed(() => {
  if (isCurrentSectionValid.value) return ''
  switch (activeSection.value) {
    case 'when':
      return t('duties.events.clone.review.problemWhen')
    case 'tasks':
      return t('duties.events.clone.tasks.tooMany', { max: MAX_TASKS })
    case 'adjust':
      return firstTaskProblem.value
    case 'announce':
      return t('duties.events.clone.review.problemNote')
    default:
      return ''
  }
})

/**
 * Move focus with the wizard.
 *
 * The button that was just pressed sits inside the step that is about to
 * unmount, so without this focus falls back to <body> and the next Tab starts
 * at the top of the page. It lands on the new step's heading rather than its
 * stepper trigger, so a screen reader reads the step's name and its
 * description — what actually changed — instead of one chip in the map.
 */
function focusStepHeading() {
  document.querySelector<HTMLElement>('[data-testid="clone-step-heading"]')?.focus()
}

/** StepperRoot counts from one; `sections` counts from zero. */
const currentStepIndex = computed(() => sections.indexOf(activeSection.value))
const currentStepNumber = computed(() => currentStepIndex.value + 1)

function isSectionValid(value: SectionName): boolean {
  const check = sectionValid[value]
  return check ? check() : true
}

/**
 * Whether a step may be opened.
 *
 * Back to anything already behind you; on to the next one once this one is
 * clean; and, after a trip backwards, forward again over steps that are still
 * valid. Never into a step whose predecessors are broken.
 */
function isStepReachable(value: SectionName): boolean {
  const target = sections.indexOf(value)
  const current = currentStepIndex.value
  if (target <= current) return true
  if (target > current + 1 && !visitedSections.value.has(value)) return false
  for (let i = current; i < target; i += 1) {
    if (!isSectionValid(sections[i])) return false
  }
  return true
}

/** A tick claims the step is done, so it needs both halves of that. */
function isStepCompleted(value: SectionName): boolean {
  return value !== activeSection.value && visitedSections.value.has(value) && isSectionValid(value)
}

/** Seen, and still wrong: the one state that has to be visible from outside. */
function stepHasProblem(value: SectionName): boolean {
  return visitedSections.value.has(value) && !isSectionValid(value)
}

function goToSection(value: SectionName) {
  if (value === activeSection.value || !isStepReachable(value)) return
  activeSection.value = value
  visitedSections.value = new Set(visitedSections.value).add(value)
  void nextTick().then(focusStepHeading)
}

/** The stepper hands back a 1-based step, or undefined while it settles. */
function onStepChange(value: number | undefined) {
  if (value === undefined) return
  const next = sections[value - 1]
  if (next) goToSection(next)
}

function goToNext() {
  const idx = currentStepIndex.value
  if (idx < 0 || idx >= sections.length - 1) return
  goToSection(sections[idx + 1])
}

function goToPrevious() {
  const idx = currentStepIndex.value
  if (idx <= 0) return
  goToSection(sections[idx - 1])
}

const isValid = computed(
  () =>
    isWhenValid.value &&
    isTasksValid.value &&
    isAdjustValid.value &&
    isAnnounceValid.value &&
    !loading.value,
)

// --- Load ---------------------------------------------------------------

const goBack = () => {
  void router.push({ name: 'my-events' })
}

/**
 * Every shift of one task.
 *
 * `GET /shifts/` caps `limit` at 200 — asking for more answers 422, which the
 * client turns into a throw — and a single task can hold more than that, so
 * this pages until the reported total is in hand.
 *
 * `complete` is false when the page cap ran out first. What is in hand is then
 * a prefix of the task, not the task, and counting it would produce exactly the
 * confidently wrong number the paging was added to prevent.
 */
async function loadShiftsForTask(
  taskId: string,
): Promise<{ shifts: ShiftRead[]; complete: boolean }> {
  const all: ShiftRead[] = []
  for (let page = 0; page < MAX_SHIFT_PAGES; page += 1) {
    const res = await get<{ data: ShiftListResponse }>({
      url: '/shifts/',
      query: { task_id: taskId, limit: SHIFT_PAGE_SIZE, skip: page * SHIFT_PAGE_SIZE },
    })
    all.push(...res.data.items)
    if (res.data.items.length === 0 || all.length >= res.data.total) {
      return { shifts: all, complete: true }
    }
  }
  return { shifts: all, complete: false }
}

/** The source task's shift blocks. Unpaged: the route returns the whole list. */
async function loadBatchesForTask(taskId: string): Promise<ShiftBatchRead[]> {
  const res = await get<{ data: ShiftBatchRead[] }>({ url: `/tasks/${taskId}/batches` })
  return res.data
}

async function loadSource() {
  loading.value = true
  try {
    const eventRes = await get<{ data: EventRead }>({ url: `/events/${sourceId}` })

    // `meta.requiresEventManager` only asks whether this account manages *some*
    // event. Whether it manages *this* one is a separate question, and the id
    // in the URL is whatever was typed there.
    if (!authStore.canManageEvent(sourceId)) {
      void router.replace({ name: 'my-events' })
      return
    }

    sourceEvent.value = eventRes.data

    const tasksRes = await get<{ data: TaskListResponse }>({
      url: '/tasks/',
      query: { event_id: sourceId, limit: 200 },
    })
    sourceTasks.value = [...tasksRes.data.items].sort((a, b) =>
      a.start_date.localeCompare(b.start_date),
    )

    // Needed for the shift counts in every section, for the copied list the
    // adjust step can show, and for the date check the backend runs first. A
    // failure here is not fatal — the backend copies the rows regardless — but
    // it is never silent: the tasks it hit are remembered so the screen says
    // "could not load" instead of "none", and says the date check did not run
    // instead of letting its silence read as approval.
    const loadedShifts = new Map<string, ShiftRead[]>()
    const loadedBatches = new Map<string, ShiftBatchRead[]>()
    const failed = new Set<string>()
    const uncheckable = new Set<string>()
    await Promise.all(
      sourceTasks.value.map(async (task) => {
        const [shiftResult, batchResult] = await Promise.allSettled([
          loadShiftsForTask(task.id),
          loadBatchesForTask(task.id),
        ])
        if (shiftResult.status === 'fulfilled' && shiftResult.value.complete) {
          loadedShifts.set(task.id, shiftResult.value.shifts)
        } else {
          loadedShifts.set(task.id, [])
          failed.add(task.id)
          uncheckable.add(task.id)
        }
        if (batchResult.status === 'fulfilled') {
          loadedBatches.set(task.id, batchResult.value)
        } else {
          loadedBatches.set(task.id, [])
          uncheckable.add(task.id)
        }
      }),
    )
    shiftsByTask.value = loadedShifts
    batchesByTask.value = loadedBatches
    shiftsUnavailable.value = failed
    rangeCheckUnavailable.value = uncheckable
    shiftsVersion.value += 1

    await applyPrefill()
  } catch (error) {
    toastApiError(error)
  } finally {
    loading.value = false
  }
}

/**
 * Fill the form in from the source event.
 *
 * The `nextTick` is load-bearing: `watch(startDate, …)` derives the end date
 * and flushes *after* the assignment that triggered it, so an end date written
 * in the same tick is overwritten a moment later.
 *
 * The configs are written *before* the selection: the template dereferences
 * `taskConfigs[task.id]` for every selected task, so a selected id with no
 * config yet is a render-time crash.
 */
async function applyPrefill() {
  const ev = sourceEvent.value
  if (!ev) return

  name.value = t('duties.events.clone.namePrefill', { name: ev.name })

  endDateTouched.value = false
  startDate.value = parseDate(addDays(ev.start_date, DEFAULT_OFFSET_DAYS))
  await nextTick()
  endDate.value = parseDate(addDays(newStartIso.value, sourceDurationDays.value))

  const offset = offsetDays.value ?? DEFAULT_OFFSET_DAYS
  const configs: Record<string, TaskConfig> = {}
  for (const task of sourceTasks.value) {
    configs[task.id] = buildTaskConfig(task, offset)
  }
  taskConfigs.value = configs
  selectedTaskIds.value = new Set(selectableTaskIds.value)
}

onMounted(loadSource)

// --- Submit -------------------------------------------------------------

async function handleSubmit() {
  if (!isValid.value || submitting.value) return
  submitting.value = true

  try {
    const tasks: EventCloneTask[] = configuredTasks.value.map((task) => {
      const cfg = taskConfigs.value[task.id]
      const entry: EventCloneTask = {
        source_task_id: task.id,
        mode: cfg.mode,
        start_date: cfg.startDate,
        end_date: cfg.endDate,
        // Task visibility is gated on membership and task status, never on the
        // event being a draft, and publishing the event does not cascade — so
        // this is the setting that decides whether the copied roster can book
        // the copy, and it is the organiser's to make.
        status: cfg.status,
      }
      // Omitted means "keep the source value", so only send what was changed.
      if (cfg.name.trim() !== task.name) entry.name = cfg.name.trim()
      if (cfg.location.trim() !== (task.location ?? '')) {
        // `_pick` only falls back on null; '' would be written to the column.
        entry.location = cfg.location.trim() || null
      }
      if (cfg.mode === 'regenerate') {
        entry.default_start_time = `${padClock(cfg.startTime)}:00`
        entry.default_end_time = `${padClock(cfg.endTime)}:00`
        entry.shift_duration_minutes = cfg.durationMinutes
        entry.people_per_shift = cfg.peoplePerShift
      }
      return entry
    })

    const body: EventCloneRequest = {
      name: name.value.trim(),
      start_date: newStartIso.value,
      end_date: newEndIso.value,
      // The request defaults to private, which would quietly demote a copy of a
      // public event. Review says which one it will be either way.
      visibility: sourceEvent.value?.visibility ?? 'private',
      copy_members: copyMembers.value,
      tasks,
      announce: {
        send: willNotify.value,
        note: willNotify.value && announceNote.value.trim() ? announceNote.value.trim() : null,
      },
    }

    const res = await post<{ data: EventCloneResponse }>({
      url: `/events/${sourceId}/clone`,
      body,
    })

    // What the server did, not what was asked for: it skips suspended members
    // and sends nothing when that leaves nobody.
    const parts = [
      t('duties.events.clone.success', {
        tasks: res.data.tasks_created,
        shifts: res.data.shifts_created,
      }),
    ]
    if (copyMembers.value) {
      parts.push(
        t(
          'duties.events.clone.successMembers',
          { count: res.data.members_copied },
          res.data.members_copied,
        ),
      )
    }
    if (willNotify.value) {
      parts.push(
        res.data.notified
          ? t('duties.events.clone.successNotified')
          : t('duties.events.clone.successNotNotified'),
      )
    }
    toast.success(parts.join(' '))
    void router.push({ name: 'event-settings', params: { eventId: res.data.event.id } })
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
        @click="goBack"
      >
        <ArrowLeft class="mr-1.5 h-4 w-4" />
        {{ t('common.actions.back') }}
      </Button>
      <h1 data-testid="page-heading" class="text-2xl font-bold tracking-tight sm:text-3xl">
        {{ t('duties.events.clone.title') }}
      </h1>
      <p class="text-muted-foreground">{{ t('duties.events.clone.subtitle') }}</p>
    </div>

    <p v-if="loading" class="py-12 text-center text-muted-foreground">
      {{ t('common.states.loading') }}
    </p>

    <div v-else-if="sourceEvent" class="space-y-6">
      <!-- Where the wizard is, and nothing else: bare above the card, because
           the map is not one of the places. -->
      <!-- Not linear: reka's own linear rule stops one step past the current
           one, which would strand a user who stepped back to fix a typo behind
           four ticked-off steps that look clickable and are not. `:disabled`
           below is the single gate, and it is the stricter of the two — a step
           is only offered once everything in front of it is clean. -->
      <Stepper
        data-testid="clone-stepper"
        class="w-full items-start gap-0"
        :linear="false"
        :model-value="currentStepNumber"
        @update:model-value="onStepChange"
      >
        <StepperItem
          v-for="(section, index) in sections"
          :key="section"
          class="relative flex w-full flex-col items-center"
          :step="index + 1"
          :completed="isStepCompleted(section)"
          :disabled="!isStepReachable(section)"
        >
          <StepperSeparator
            v-if="index < sections.length - 1"
            class="absolute left-[calc(50%_+_1.25rem)] right-[calc(-50%_+_1.25rem)] top-5 h-0.5 rounded-full bg-border group-data-[state=completed]:bg-primary/50"
          />
          <StepperTrigger
            :data-testid="`step-${section}`"
            class="outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            <StepperIndicator
              class="h-8 w-8 border bg-background text-sm font-semibold text-muted-foreground group-data-[state=completed]:border-primary/40 group-data-[state=completed]:bg-primary/10 group-data-[state=completed]:text-primary"
              :class="
                stepHasProblem(section)
                  ? 'border-destructive/60 bg-destructive/10 text-destructive group-data-[state=active]:bg-destructive group-data-[state=active]:text-destructive-foreground'
                  : ''
              "
            >
              <TriangleAlert v-if="stepHasProblem(section)" class="h-4 w-4" aria-hidden="true" />
              <Check v-else-if="isStepCompleted(section)" class="h-4 w-4" aria-hidden="true" />
              <template v-else>{{ index + 1 }}</template>
            </StepperIndicator>
            <!-- Below sm the words go and the numbers stay: five labels do not
                 fit a phone, and the footer says which step this is in full. -->
            <!-- Weight carries "you are here" and italics carry "not yet",
                 so the three states survive a reader who cannot tell the
                 accent hue from the muted one. -->
            <StepperTitle
              class="hidden text-xs sm:block"
              :class="
                section === activeSection
                  ? 'font-semibold text-foreground'
                  : isStepReachable(section)
                    ? 'font-medium text-muted-foreground'
                    : 'font-normal italic text-muted-foreground/60'
              "
            >
              {{ t(`duties.events.clone.steps.${section}`) }}
            </StepperTitle>
          </StepperTrigger>
        </StepperItem>
      </Stepper>

      <!-- One card, one step. The other four are not rendered at all. -->
      <Card data-testid="clone-step-card">
        <CardHeader :class="showSelectedCount ? 'grid-cols-[1fr_auto]' : ''">
          <!-- Focus lands here on every step change, so the heading and the
               description below it are what a screen reader reads out. -->
          <CardTitle
            data-testid="clone-step-heading"
            tabindex="-1"
            class="flex items-center gap-2 outline-none"
          >
            <component :is="stepIcons[activeSection]" class="h-5 w-5 text-primary" />
            {{ t(`duties.events.clone.sections.${activeSection}`) }}
          </CardTitle>
          <CardDescription>
            {{ t(`duties.events.clone.sections.${activeSection}Desc`) }}
          </CardDescription>
          <CardAction v-if="showSelectedCount">
            <Badge variant="secondary" data-testid="clone-selected-count">
              {{
                t(
                  'duties.events.clone.taskCount',
                  { count: selectedTasks.length },
                  selectedTasks.length,
                )
              }}
            </Badge>
          </CardAction>
        </CardHeader>

        <CardContent>
          <!-- Step 1: When -->
          <div v-if="activeSection === 'when'" data-testid="section-when" class="space-y-4">
            <!-- What is being copied, read only -->
            <div class="rounded-lg border bg-muted/40 p-3" data-testid="clone-source-summary">
              <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {{ t('duties.events.clone.source.label') }}
              </p>
              <p class="mt-1 font-medium">{{ sourceEvent.name }}</p>
              <p class="text-sm text-muted-foreground">
                {{ dateLabel(sourceEvent.start_date) }} –
                {{ dateLabel(sourceEvent.end_date) }}
              </p>
              <p class="mt-2 text-sm text-muted-foreground">
                {{
                  t(
                    'duties.events.clone.source.contents',
                    { tasks: sourceTasks.length },
                    sourceTasks.length,
                  )
                }}
              </p>
              <p class="mt-2 text-sm font-medium" data-testid="clone-source-untouched">
                {{ t('duties.events.clone.source.untouched', { name: sourceEvent.name }) }}
              </p>
            </div>

            <div class="space-y-2">
              <Label for="clone-name">{{ t('duties.events.fields.name') }} *</Label>
              <Input
                id="clone-name"
                v-model="name"
                data-testid="input-clone-name"
                :placeholder="t('duties.events.createView.namePlaceholder')"
              />
            </div>

            <!-- No mutual clamp: both boxes are prefilled, so a calendar that
                 hard-disables every day past the other one would be live from
                 first paint and the dates could not be moved at all. Order is
                 checked in script instead. -->
            <div class="grid gap-4 sm:grid-cols-2">
              <div class="space-y-2" data-testid="picker-clone-start-date">
                <Label>{{ t('duties.events.fields.startDate') }} *</Label>
                <DatePicker v-model="startDate" :placeholder="t('duties.events.pickDate')" />
              </div>
              <div class="space-y-2" data-testid="picker-clone-end-date">
                <Label>{{ t('duties.events.fields.endDate') }} *</Label>
                <DatePicker
                  :model-value="endDate"
                  :highlight="startDate"
                  :placeholder="t('duties.events.pickDate')"
                  @update:model-value="
                    (value: DateValue | undefined) => {
                      endDate = value
                      endDateTouched = true
                    }
                  "
                />
              </div>
            </div>

            <div class="space-y-1 text-sm" data-testid="clone-offset-summary">
              <p v-if="offsetDays !== null" class="text-muted-foreground">
                {{
                  offsetDays === 0
                    ? t('duties.events.clone.offset.same')
                    : offsetDays > 0
                      ? t('duties.events.clone.offset.later', { days: offsetDays }, offsetDays)
                      : t('duties.events.clone.offset.earlier', { days: -offsetDays }, -offsetDays)
                }}
              </p>
              <p v-if="keepsWeekday" class="text-muted-foreground">
                {{ t('duties.events.clone.offset.sameWeekday') }}
              </p>
              <p v-if="newDayCount" class="text-xs text-muted-foreground">
                {{ t('duties.events.clone.lengthHint', { days: newDayCount }, newDayCount) }}
              </p>
            </div>
          </div>

          <!-- Step 2: Tasks -->
          <div v-else-if="activeSection === 'tasks'" data-testid="section-tasks" class="space-y-4">
            <p v-if="sourceTasks.length === 0" class="py-6 text-center text-muted-foreground">
              {{ t('duties.events.clone.tasks.none') }}
            </p>

            <!-- Alongside the list, never instead of it: the checkboxes are the
                 only way back under the limit. -->
            <p
              v-if="!isTasksValid"
              class="rounded-lg border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive"
              data-testid="clone-too-many-tasks"
            >
              {{ t('duties.events.clone.tasks.tooMany', { max: MAX_TASKS }) }}
            </p>

            <label
              v-if="sourceTasks.length > 0"
              class="flex cursor-pointer items-center gap-2 rounded-lg border bg-muted/40 px-3 py-2"
            >
              <Checkbox
                data-testid="check-all-tasks"
                :model-value="selectAllState"
                @update:model-value="toggleAllTasks"
              />
              <span class="text-sm font-medium">{{
                t('duties.events.clone.tasks.selectAll')
              }}</span>
            </label>

            <div class="space-y-2">
              <label
                v-for="task in sourceTasks"
                :key="task.id"
                class="flex cursor-pointer items-start gap-3 rounded-lg border bg-muted/40 p-3"
                :data-testid="`check-task-${task.id}`"
              >
                <Checkbox
                  class="mt-0.5"
                  :model-value="selectedTaskIds.has(task.id)"
                  @update:model-value="
                    (value: boolean | 'indeterminate') => toggleTask(task.id, value)
                  "
                />
                <span class="min-w-0 flex-1">
                  <span class="flex flex-wrap items-center gap-2">
                    <span class="font-medium">{{ task.name }}</span>
                    <Badge v-if="task.category" variant="outline">{{ task.category }}</Badge>
                  </span>
                  <span v-if="task.location" class="mt-0.5 block text-xs text-muted-foreground">
                    {{ task.location }}
                  </span>
                  <span class="mt-1 block text-xs text-muted-foreground">
                    {{ dateLabel(addDays(task.start_date, offsetDays ?? 0)) }} –
                    {{ dateLabel(addDays(task.end_date, offsetDays ?? 0)) }}
                  </span>
                  <span
                    v-if="shiftsUnavailable.has(task.id)"
                    class="mt-0.5 block text-xs text-destructive"
                    :data-testid="`shifts-unavailable-${task.id}`"
                  >
                    {{ t('duties.events.clone.tasks.shiftCountUnknown') }}
                  </span>
                  <span v-else class="mt-0.5 block text-xs text-muted-foreground">
                    {{
                      t(
                        'duties.events.clone.tasks.shiftCount',
                        { count: sourceShiftCount(task.id) },
                        sourceShiftCount(task.id),
                      )
                    }}
                  </span>
                </span>
              </label>
            </div>

            <!-- The roster -->
            <div class="flex items-start justify-between gap-4 rounded-lg border bg-muted/40 p-3">
              <div class="min-w-0">
                <p
                  id="clone-copy-members-label"
                  class="flex items-center gap-2 text-sm font-medium"
                >
                  <Users class="h-4 w-4 text-muted-foreground" />
                  {{ t('duties.events.clone.tasks.copyMembers') }}
                </p>
                <p class="mt-1 text-xs text-muted-foreground">
                  {{
                    t(
                      'duties.events.clone.tasks.copyMembersHint',
                      { count: otherMemberCount },
                      otherMemberCount,
                    )
                  }}
                </p>
              </div>
              <Switch
                data-testid="switch-copy-members"
                :aria-label="t('duties.events.clone.tasks.copyMembers')"
                aria-describedby="clone-copy-members-label"
                :model-value="copyMembers"
                @update:model-value="(value: boolean) => (copyMembers = value)"
              />
            </div>

            <div class="rounded-lg border border-dashed p-3">
              <p class="text-sm font-medium">{{ t('duties.events.clone.tasks.notCopied') }}</p>
              <ul class="mt-1 list-disc space-y-0.5 pl-5 text-xs text-muted-foreground">
                <li>{{ t('duties.events.clone.tasks.notCopiedItems.bookings') }}</li>
                <li>{{ t('duties.events.clone.tasks.notCopiedItems.availability') }}</li>
                <li>{{ t('duties.events.clone.tasks.notCopiedItems.invitations') }}</li>
                <li>{{ t('duties.events.clone.tasks.notCopiedItems.joinRequests') }}</li>
                <li>{{ t('duties.events.clone.tasks.notCopiedItems.reminders') }}</li>
                <li>{{ t('duties.events.clone.tasks.notCopiedItems.featured') }}</li>
              </ul>
            </div>
          </div>

          <!-- Step 3: Adjust -->
          <div
            v-else-if="activeSection === 'adjust'"
            data-testid="section-adjust"
            class="space-y-4"
          >
            <!-- The per-task errors live inside panels that start closed, so
                 the step says up front that one of them is broken. -->
            <div
              v-if="hasTaskProblems"
              class="flex items-start gap-2 rounded-lg border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive"
            >
              <TriangleAlert class="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <p class="min-w-0 flex-1">
                {{
                  t(
                    'duties.events.clone.adjust.problemStrip',
                    { count: problemTaskCount },
                    problemTaskCount,
                  )
                }}
              </p>
              <Badge variant="destructive" data-testid="badge-adjust-problems">
                {{ t('duties.events.clone.adjust.problemBadge') }}
              </Badge>
            </div>
            <p v-if="configuredTasks.length === 0" class="py-6 text-center text-muted-foreground">
              {{ t('duties.events.clone.adjust.none') }}
            </p>

            <Collapsible
              v-for="task in configuredTasks"
              :key="task.id"
              v-model:open="taskConfigs[task.id].expanded"
              class="rounded-lg border bg-muted/40"
              :class="taskProblems[task.id] ? 'border-destructive' : ''"
            >
              <CollapsibleTrigger
                class="flex w-full items-center gap-3 p-3 text-left"
                :data-testid="`btn-adjust-task-${task.id}`"
              >
                <span class="min-w-0 flex-1">
                  <span class="block truncate text-sm font-medium">
                    {{ taskConfigs[task.id].name || task.name }}
                  </span>
                  <span class="mt-0.5 block text-xs text-muted-foreground">
                    {{ dateLabel(taskConfigs[task.id].startDate) }} –
                    {{ dateLabel(taskConfigs[task.id].endDate) }} ·
                    {{
                      countUnknownFor(task.id)
                        ? t('duties.events.clone.tasks.shiftCountUnknown')
                        : t(
                            'duties.events.clone.adjust.willCreate',
                            { count: shiftCountFor(task.id) },
                            shiftCountFor(task.id),
                          )
                    }}
                  </span>
                </span>
                <!-- A per-task error lives inside this panel, which starts
                     closed — so the closed row has to say so itself. -->
                <Badge
                  v-if="taskProblems[task.id]"
                  variant="destructive"
                  :data-testid="`badge-task-problem-${task.id}`"
                >
                  {{ t('duties.events.clone.adjust.problemBadge') }}
                </Badge>
                <Badge variant="secondary">
                  {{ t(`duties.events.clone.adjust.mode.${taskConfigs[task.id].mode}.short`) }}
                </Badge>
                <Badge variant="outline" :data-testid="`badge-task-status-${task.id}`">
                  {{ t(`duties.events.clone.adjust.status.${taskConfigs[task.id].status}.short`) }}
                </Badge>
                <ChevronDown
                  class="h-4 w-4 shrink-0 text-muted-foreground transition-transform"
                  :class="taskConfigs[task.id].expanded ? 'rotate-180' : ''"
                />
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div class="space-y-4 border-t p-3">
                  <div class="grid gap-4 sm:grid-cols-2">
                    <div class="space-y-2">
                      <Label :for="`clone-task-name-${task.id}`">
                        {{ t('duties.tasks.fields.name') }}
                      </Label>
                      <Input
                        :id="`clone-task-name-${task.id}`"
                        v-model="taskConfigs[task.id].name"
                        :data-testid="`input-task-name-${task.id}`"
                      />
                    </div>
                    <div class="space-y-2">
                      <Label :for="`clone-task-location-${task.id}`">
                        {{ t('duties.tasks.fields.location') }}
                      </Label>
                      <Input
                        :id="`clone-task-location-${task.id}`"
                        v-model="taskConfigs[task.id].location"
                        :data-testid="`input-task-location-${task.id}`"
                      />
                    </div>
                  </div>

                  <p
                    v-if="copyKeepsOldLabels(task)"
                    class="text-xs text-muted-foreground"
                    :data-testid="`copy-keeps-labels-${task.id}`"
                  >
                    {{ t('duties.events.clone.adjust.copyKeepsOldLabels') }}
                  </p>

                  <div class="grid gap-4 sm:grid-cols-2">
                    <div class="space-y-2" :data-testid="`picker-task-start-${task.id}`">
                      <Label>{{ t('duties.tasks.fields.startDate') }}</Label>
                      <DatePicker
                        :model-value="taskDateValue(taskConfigs[task.id].startDate)"
                        :min-value="startDate"
                        :max-value="endDate"
                        :placeholder="t('duties.events.pickDate')"
                        @update:model-value="
                          (value: DateValue | undefined) => setTaskDate(task.id, 'startDate', value)
                        "
                      />
                    </div>
                    <div class="space-y-2" :data-testid="`picker-task-end-${task.id}`">
                      <Label>{{ t('duties.tasks.fields.endDate') }}</Label>
                      <DatePicker
                        :model-value="taskDateValue(taskConfigs[task.id].endDate)"
                        :min-value="startDate"
                        :max-value="endDate"
                        :placeholder="t('duties.events.pickDate')"
                        @update:model-value="
                          (value: DateValue | undefined) => setTaskDate(task.id, 'endDate', value)
                        "
                      />
                    </div>
                  </div>

                  <div class="space-y-2">
                    <Label>{{ t('duties.events.clone.adjust.modeLabel') }}</Label>
                    <RadioGroup
                      v-model="taskConfigs[task.id].mode"
                      class="grid gap-2 sm:grid-cols-2"
                      :data-testid="`radio-task-mode-${task.id}`"
                    >
                      <div
                        v-for="option in ['copy', 'regenerate'] as const"
                        :key="option"
                        class="flex items-start gap-2 rounded-lg border p-3"
                      >
                        <RadioGroupItem
                          :id="`mode-${option}-${task.id}`"
                          :value="option"
                          class="mt-0.5"
                        />
                        <Label :for="`mode-${option}-${task.id}`" class="cursor-pointer">
                          <span class="block text-sm font-medium">
                            {{ t(`duties.events.clone.adjust.mode.${option}.label`) }}
                          </span>
                          <span class="mt-0.5 block text-xs font-normal text-muted-foreground">
                            {{ t(`duties.events.clone.adjust.mode.${option}.hint`) }}
                          </span>
                        </Label>
                      </div>
                    </RadioGroup>
                  </div>

                  <!-- The only thing that decides whether anyone can book the
                       copy: publishing the event leaves its tasks alone. -->
                  <div class="space-y-2">
                    <Label>{{ t('duties.events.clone.adjust.statusLabel') }}</Label>
                    <RadioGroup
                      v-model="taskConfigs[task.id].status"
                      class="grid gap-2 sm:grid-cols-2"
                      :data-testid="`radio-task-status-${task.id}`"
                    >
                      <div
                        v-for="option in ['draft', 'published'] as const"
                        :key="option"
                        class="flex items-start gap-2 rounded-lg border p-3"
                      >
                        <RadioGroupItem
                          :id="`status-${option}-${task.id}`"
                          :value="option"
                          class="mt-0.5"
                        />
                        <Label :for="`status-${option}-${task.id}`" class="cursor-pointer">
                          <span class="block text-sm font-medium">
                            {{ t(`duties.events.clone.adjust.status.${option}.label`) }}
                          </span>
                          <span class="mt-0.5 block text-xs font-normal text-muted-foreground">
                            {{ t(`duties.events.clone.adjust.status.${option}.hint`) }}
                          </span>
                        </Label>
                      </div>
                    </RadioGroup>
                  </div>

                  <div v-if="taskConfigs[task.id].mode === 'regenerate'" class="space-y-4">
                    <div class="grid gap-4 sm:grid-cols-2">
                      <div class="space-y-2">
                        <Label>{{ t('duties.tasks.createView.schedule.defaultStartTime') }}</Label>
                        <TimePicker
                          v-model="taskConfigs[task.id].startTime"
                          class="w-full"
                          :placeholder="t('duties.events.fields.timeOptional')"
                        />
                      </div>
                      <div class="space-y-2">
                        <Label>{{ t('duties.tasks.createView.schedule.defaultEndTime') }}</Label>
                        <TimePicker
                          v-model="taskConfigs[task.id].endTime"
                          class="w-full"
                          :placeholder="t('duties.events.fields.timeOptional')"
                        />
                      </div>
                    </div>
                    <div class="grid gap-4 sm:grid-cols-2">
                      <div class="space-y-2" :data-testid="`select-duration-${task.id}`">
                        <Label>{{ t('duties.tasks.createView.schedule.slotDuration') }}</Label>
                        <Select v-model="taskConfigs[task.id].durationMinutes">
                          <SelectTrigger>
                            <SelectValue
                              :placeholder="t('duties.tasks.createView.schedule.slotDuration')"
                            />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem v-for="d in durationOptions(task.id)" :key="d" :value="d">
                              {{ t('duties.tasks.createView.schedule.minutes', { n: d }) }}
                            </SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div class="space-y-2">
                        <Label :for="`clone-people-${task.id}`">
                          {{ t('duties.tasks.createView.schedule.peoplePerShift') }}
                        </Label>
                        <Input
                          :id="`clone-people-${task.id}`"
                          v-model.number="taskConfigs[task.id].peoplePerShift"
                          type="number"
                          min="1"
                          :data-testid="`input-people-${task.id}`"
                        />
                      </div>
                    </div>
                  </div>

                  <p
                    v-if="taskProblems[task.id]"
                    class="text-sm text-destructive"
                    :data-testid="`error-task-${task.id}`"
                  >
                    {{ taskProblems[task.id] }}
                  </p>

                  <!-- Silence from the date check means "nothing to check", not
                       "the dates are fine", whenever the rows behind it are
                       missing — so it has to say which one it is. -->
                  <p
                    v-else-if="rangeCheckUnavailable.has(task.id)"
                    class="text-sm text-amber-600 dark:text-amber-500"
                    :data-testid="`range-check-unknown-${task.id}`"
                  >
                    {{ t('duties.events.clone.adjust.rangeCheckUnavailable') }}
                  </p>

                  <div class="rounded-lg border p-3">
                    <p
                      v-if="countUnknownFor(task.id)"
                      class="text-sm text-destructive"
                      :data-testid="`shift-count-${task.id}`"
                    >
                      {{ t('duties.events.clone.adjust.shiftsUnknown') }}
                    </p>
                    <template v-else>
                      <p class="text-sm font-medium" :data-testid="`shift-count-${task.id}`">
                        {{
                          t(
                            'duties.events.clone.adjust.willCreate',
                            { count: shiftCountFor(task.id) },
                            shiftCountFor(task.id),
                          )
                        }}
                      </p>
                      <!-- The backend regenerates per cloned batch, over each
                           batch's own range; this preview runs the whole task
                           window, so it can only ever be an upper bound. -->
                      <p
                        v-if="taskConfigs[task.id].mode === 'regenerate'"
                        class="mt-1 text-xs text-muted-foreground"
                        :data-testid="`estimate-note-${task.id}`"
                      >
                        {{ t('duties.events.clone.adjust.estimateNote') }}
                      </p>
                    </template>
                    <Collapsible v-if="shiftCountFor(task.id) > 0" class="mt-2">
                      <CollapsibleTrigger
                        class="text-sm font-medium text-primary underline-offset-4 hover:underline"
                        :data-testid="`btn-show-shifts-${task.id}`"
                      >
                        {{ t('duties.events.clone.adjust.showShifts') }}
                      </CollapsibleTrigger>
                      <CollapsibleContent>
                        <div class="pt-3">
                          <p class="mb-2 text-xs text-muted-foreground">
                            {{ t('duties.events.clone.adjust.readOnlyNote') }}
                          </p>
                          <ShiftPreviewGrid
                            :shifts-by-date="shiftsByDateFor(task.id)"
                            :is-shift-excluded="neverExcluded"
                            readonly
                          />
                        </div>
                      </CollapsibleContent>
                    </Collapsible>
                  </div>
                </div>
              </CollapsibleContent>
            </Collapsible>
          </div>

          <!-- Step 4: Announce -->
          <div
            v-else-if="activeSection === 'announce'"
            data-testid="section-announce"
            class="space-y-4"
          >
            <!-- No roster, no audience: the switch would do nothing, so it is
                 not offered at all. -->
            <p
              v-if="!canAnnounce"
              class="rounded-lg border border-dashed p-3 text-sm text-muted-foreground"
              data-testid="announce-nobody"
            >
              {{
                copyMembers
                  ? t('duties.events.clone.announce.nobodyElse')
                  : t('duties.events.clone.announce.noRoster')
              }}
            </p>

            <template v-else>
              <div class="flex items-start justify-between gap-4 rounded-lg border bg-muted/40 p-3">
                <div class="min-w-0">
                  <p id="clone-announce-label" class="text-sm font-medium">
                    {{ t('duties.events.clone.announce.toggle') }}
                  </p>
                  <p class="mt-1 text-xs text-muted-foreground">
                    {{
                      t(
                        'duties.events.clone.announce.toggleHint',
                        { count: audienceCount },
                        audienceCount,
                      )
                    }}
                  </p>
                </div>
                <Switch
                  data-testid="switch-announce"
                  :aria-label="t('duties.events.clone.announce.toggle')"
                  aria-describedby="clone-announce-label"
                  :model-value="announceSend"
                  @update:model-value="(value: boolean) => (announceSend = value)"
                />
              </div>

              <div v-if="announceSend" class="space-y-2">
                <Label for="clone-note">{{ t('duties.events.clone.announce.note') }}</Label>
                <!-- No native maxlength: it silently truncates a pasted note and
                     leaves the counter reading a comfortable 500 of 500. -->
                <Textarea
                  id="clone-note"
                  v-model="announceNote"
                  data-testid="input-announce-note"
                  :rows="3"
                  :placeholder="t('duties.events.clone.announce.notePlaceholder')"
                />
                <p
                  class="text-xs"
                  data-testid="announce-note-counter"
                  :class="noteTooLong ? 'text-destructive' : 'text-muted-foreground'"
                >
                  {{
                    t('duties.events.clone.announce.noteCounter', {
                      used: announceNote.length,
                      max: NOTE_MAX_LENGTH,
                    })
                  }}
                </p>
              </div>
            </template>
          </div>

          <!-- Step 5: Review -->
          <div v-else data-testid="section-review" class="space-y-4">
            <div class="grid gap-3 sm:grid-cols-2" data-testid="review-summary">
              <div class="rounded-lg border bg-muted/40 p-3">
                <p class="text-xs uppercase tracking-wide text-muted-foreground">
                  {{ t('duties.events.clone.review.tasks') }}
                </p>
                <p class="text-lg font-semibold">{{ configuredTasks.length }}</p>
              </div>
              <div class="rounded-lg border bg-muted/40 p-3">
                <p class="text-xs uppercase tracking-wide text-muted-foreground">
                  {{ t('duties.events.clone.review.shifts') }}
                </p>
                <p class="text-lg font-semibold" data-testid="review-shift-total">
                  {{ totalsIncomplete ? '–' : totalShifts }}
                </p>
              </div>
              <div class="rounded-lg border bg-muted/40 p-3">
                <p class="text-xs uppercase tracking-wide text-muted-foreground">
                  {{ t('duties.events.clone.review.spots') }}
                </p>
                <p class="text-lg font-semibold">{{ totalsIncomplete ? '–' : totalSpots }}</p>
              </div>
              <div class="rounded-lg border bg-muted/40 p-3">
                <p class="text-xs uppercase tracking-wide text-muted-foreground">
                  {{ t('duties.events.clone.review.people') }}
                </p>
                <p class="text-lg font-semibold">{{ copyMembers ? audienceCount : 0 }}</p>
              </div>
            </div>

            <p
              v-if="totalsIncomplete"
              class="rounded-lg border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive"
              data-testid="review-shifts-unknown"
            >
              {{ t('duties.events.clone.review.shiftsUnknown') }}
            </p>

            <p class="text-sm text-muted-foreground" data-testid="review-audience">
              {{
                willNotify
                  ? t(
                      'duties.events.clone.review.willTell',
                      { count: audienceCount },
                      audienceCount,
                    )
                  : t('duties.events.clone.review.willNotTell')
              }}
            </p>

            <p class="text-sm font-medium" data-testid="review-untouched">
              {{ t('duties.events.clone.review.untouched', { name: sourceEvent.name }) }}
            </p>

            <p class="text-sm text-muted-foreground" data-testid="review-draft-note">
              {{ t('duties.events.clone.review.draftNote') }}
            </p>

            <!-- The booking story, told from what was actually chosen in the
                 adjust step rather than from the event's own draft status. -->
            <p v-if="taskStatusNote" class="text-sm font-medium" data-testid="review-task-status">
              {{ taskStatusNote }}
            </p>

            <p class="text-sm text-muted-foreground" data-testid="review-visibility">
              {{
                sourceEvent.visibility === 'public'
                  ? t('duties.events.clone.review.visibilityPublic')
                  : t('duties.events.clone.review.visibilityPrivate')
              }}
            </p>

            <div v-if="configuredTasks.length > 0" class="space-y-2">
              <p class="text-sm font-medium">{{ t('duties.events.clone.review.perTask') }}</p>
              <div
                v-for="task in configuredTasks"
                :key="task.id"
                class="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-muted/40 p-3 text-sm"
                :data-testid="`review-task-${task.id}`"
              >
                <span class="min-w-0">
                  <span class="block font-medium">
                    {{ taskConfigs[task.id].name || task.name }}
                  </span>
                  <span class="block text-xs text-muted-foreground">
                    {{ dateLabel(taskConfigs[task.id].startDate) }} –
                    {{ dateLabel(taskConfigs[task.id].endDate) }}
                    <template v-if="taskConfigs[task.id].mode === 'regenerate'">
                      ·
                      {{
                        formatTimeRange(
                          taskConfigs[task.id].startTime,
                          taskConfigs[task.id].endTime,
                        )
                      }}
                    </template>
                  </span>
                </span>
                <span class="flex items-center gap-2">
                  <Badge variant="outline">
                    {{ t(`duties.events.clone.adjust.mode.${taskConfigs[task.id].mode}.short`) }}
                  </Badge>
                  <Badge variant="outline" :data-testid="`review-task-status-${task.id}`">
                    {{
                      t(`duties.events.clone.adjust.status.${taskConfigs[task.id].status}.short`)
                    }}
                  </Badge>
                  <Badge variant="secondary">
                    {{
                      countUnknownFor(task.id)
                        ? t('duties.events.clone.tasks.shiftCountUnknown')
                        : t(
                            'duties.events.clone.review.shiftCount',
                            { count: shiftCountFor(task.id) },
                            shiftCountFor(task.id),
                          )
                    }}
                  </Badge>
                </span>
              </div>
            </div>
          </div>
        </CardContent>

        <!-- One footer for every step: why you cannot leave it yet, where you
             are, and the ways out. A column on a phone and a single row from sm
             up, with the forward action pinned right the way every other form
             view in the app places its actions. -->
        <CardFooter class="flex-col items-stretch gap-3 border-t">
          <!-- Whichever step is holding things up is the one on screen, so the
               reason sits with the button it has switched off. -->
          <p
            v-if="stepBlockedReason"
            class="flex items-start gap-2 rounded-lg border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive"
            data-testid="clone-step-blocked"
          >
            <TriangleAlert class="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span class="min-w-0 flex-1">{{ stepBlockedReason }}</span>
          </p>

          <div
            class="flex flex-col-reverse gap-3 sm:grid sm:grid-cols-[1fr_auto_1fr] sm:items-center sm:gap-4"
          >
            <Button
              data-testid="btn-step-back"
              variant="ghost"
              class="w-full sm:w-auto sm:justify-self-start"
              :disabled="currentStepIndex === 0"
              @click="goToPrevious"
            >
              <ArrowLeft class="mr-1.5 h-4 w-4" />
              {{ t('common.actions.previousStep') }}
            </Button>

            <!-- The live region for the whole wizard: reka's own is hidden in
                 Stepper.vue because it is hard-coded English. -->
            <p
              class="text-center text-xs text-muted-foreground"
              data-testid="clone-step-position"
              role="status"
              aria-live="polite"
              aria-atomic="true"
            >
              {{
                t('duties.events.clone.stepPosition', {
                  current: currentStepNumber,
                  total: sections.length,
                })
              }}
            </p>

            <div
              class="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:gap-3 sm:justify-self-end"
            >
              <template v-if="activeSection === 'review'">
                <Button
                  data-testid="btn-cancel"
                  variant="outline"
                  class="w-full sm:w-auto"
                  @click="goBack"
                >
                  {{ t('common.actions.cancel') }}
                </Button>
                <Button
                  data-testid="btn-submit"
                  class="w-full sm:w-auto"
                  :disabled="!isValid || submitting"
                  @click="handleSubmit"
                >
                  <Copy class="mr-2 h-4 w-4" />
                  {{ submitting ? t('common.states.saving') : t('duties.events.clone.submit') }}
                </Button>
              </template>
              <Button
                v-else
                data-testid="btn-step-next"
                class="w-full sm:w-auto"
                :disabled="!isCurrentSectionValid"
                @click="goToNext"
              >
                {{ t('common.actions.next') }}
              </Button>
            </div>
          </div>
        </CardFooter>
      </Card>
    </div>
  </div>
</template>
