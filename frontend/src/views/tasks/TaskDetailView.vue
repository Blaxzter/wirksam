<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import type { DateValue } from '@internationalized/date'
import {
  ArrowLeft,
  CalendarCheck,
  CalendarDays,
  CalendarPlus,
  ChevronDown,
  Ellipsis,
  EyeOff,
  Lock,
  MapPin,
  Pencil,
  Plus,
  Printer,
  Tag,
  Ticket,
  Trash2,
  UsersRound,
} from '@lucide/vue'
import { useMediaQuery } from '@vueuse/core'
import { I18nT, useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'
import { useBreadcrumbStore } from '@/stores/breadcrumb'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'
import { useFormatters } from '@/composables/useFormatters'
import { useMenuAction } from '@/composables/useMenuAction'

import { Alert, AlertDescription } from '@/components/ui/alert'
import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { DatePicker } from '@/components/ui/date-picker'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import Input from '@/components/ui/input/Input.vue'
import Label from '@/components/ui/label/Label.vue'
import {
  RESPONSIVE_DIALOG_MOBILE_QUERY,
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'
import Separator from '@/components/ui/separator/Separator.vue'
import { TimePicker } from '@/components/ui/time-picker'

import EventZoneHint from '@/components/events/EventZoneHint.vue'
import { joinNames } from '@/components/events/teams/teamHelpers'
import LocationFormDialog from '@/components/locations/LocationFormDialog.vue'
import LocationPicker from '@/components/locations/LocationPicker.vue'
import DeleteConfirmationDialog from '@/components/tasks/DeleteConfirmationDialog.vue'
import ShiftDetailDialog from '@/components/tasks/ShiftDetailDialog.vue'
import StatusDropdown from '@/components/tasks/StatusDropdown.vue'
import TeamJoinButton from '@/components/tasks/TeamJoinButton.vue'
import TaskActionSheet, {
  type TaskSheetAction,
} from '@/components/tasks/detail/TaskActionSheet.vue'
import TaskInChargeCard from '@/components/tasks/detail/TaskInChargeCard.vue'
import TaskShiftTile from '@/components/tasks/detail/TaskShiftTile.vue'
import TaskVouchersCard from '@/components/tasks/detail/TaskVouchersCard.vue'
import TaskManagersDialog from '@/components/tasks/managers/TaskManagersDialog.vue'
import TaskVoucherSettingsDialog from '@/components/tasks/vouchers/TaskVoucherSettingsDialog.vue'
import HintTooltip from '@/components/utils/HintTooltip.vue'
import VenueMiniMap from '@/components/venue-map/VenueMiniMap.vue'

import type {
  BookingRead,
  LocationDetailRead,
  LocationRead,
  MyBookingsListResponse,
  ShiftBatchRead,
  ShiftListResponse,
  ShiftRead,
  TaskRead,
} from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { formatDate } from '@/lib/format'
import { shiftHasEnded, shiftHasStarted } from '@/lib/shift-time'
import { sharedLocationId as sharedLocationIdOf } from '@/lib/venue-map'

const { t, locale } = useI18n()
const { formatTime, formatDateLabel, formatDaySpan } = useFormatters()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const breadcrumbStore = useBreadcrumbStore()
const { get, post, patch, delete: del } = useAuthenticatedClient()
const { confirm, confirmDestructive } = useDialog()

const eventId = computed(() => route.params.eventId as string)

/** Edit the task and its shifts: organisers and the task's people in charge. */
const canManageTask = computed(() => task.value?.can_manage ?? false)
/**
 * Add, move and delete its shifts: organisers, and its people in charge unless
 * the task earns vouchers and the event keeps those shifts with the organisers.
 */
const canManageShifts = computed(() => task.value?.can_manage_shifts ?? false)
/** Publish, delete, name people in charge, edit the event's location: organisers only. */
const canAdminEvent = computed(() => authStore.canManageEvent(task.value?.event_id))

/** The viewer is in charge of this task without being an organiser. */
const isManagerOnly = computed(
  () =>
    !canAdminEvent.value &&
    !!authStore.profile?.id &&
    (task.value?.managers ?? []).some((m) => m.user_id === authStore.profile?.id),
)

const showManagersDialog = ref(false)
const showVoucherSettings = ref(false)

/**
 * The phone layout, on the same line as the bottom navigation and the
 * dialogs that turn into sheets. Decided once here rather than with CSS, so
 * the page never renders the phone and the desktop header side by side (and
 * every `data-testid` in them twice).
 */
const isPhone = useMediaQuery(RESPONSIVE_DIALOG_MOBILE_QUERY)

const myId = computed(() => authStore.profile?.id ?? null)

/** The person in charge may change the details but not the shifts. */
const shiftsLocked = computed(() => canManageTask.value && !canManageShifts.value)

/** Who runs the task: always for organisers (to name someone), else once someone does. */
const showInChargeCard = computed(
  () => canAdminEvent.value || (task.value?.managers?.length ?? 0) > 0,
)
/** How vouchers work here, once the task earns or takes any. */
const showVouchersCard = computed(
  () => (task.value?.vouchers_per_shift ?? 0) > 0 || !!task.value?.is_voucher_point,
)

const inChargeCard = ref<InstanceType<typeof TaskInChargeCard> | null>(null)

// Withdrawing or sending an invitation in the dialog changes no `managers`,
// so the card's list of open invitations is fetched again once it closes.
watch(showManagersDialog, (open) => {
  if (!open) void inChargeCard.value?.reloadInvitations()
})

const printRoute = computed(() => ({ name: 'print-task', params: { eventId: task.value?.id } }))

/** The days the task runs, as the header line shows them. */
const daySpan = computed(() => formatDaySpan(task.value?.start_date, task.value?.end_date))

/** Who may book: the team the task is reserved for, or everyone in the event. */
const audience = computed(() => task.value?.team_name || t('duties.tasks.detail.audienceAll'))

/** "Friday, 17 July" over a day's shifts; shorter on a phone. */
const dayLabel = (date: string) =>
  formatDateLabel(date, {
    weekday: isPhone.value ? 'short' : 'long',
    day: 'numeric',
    month: 'long',
  })

// --- Phone sheets: the organiser's ⋯ menu and "Add shifts" ---
const moreSheetOpen = ref(false)
const addShiftsSheetOpen = ref(false)

const moreActions = computed<TaskSheetAction[]>(() => [
  {
    key: 'managers',
    label: t('duties.tasks.managers.manage'),
    icon: UsersRound,
    testid: 'btn-task-managers-mobile',
  },
  {
    key: 'vouchers',
    label: t('vouchers.settings.open'),
    icon: Ticket,
    testid: 'btn-task-vouchers-mobile',
  },
  {
    key: 'print',
    label: t('duties.tasks.detail.print'),
    icon: Printer,
    testid: 'btn-print-mobile',
  },
  {
    key: 'delete',
    label: t('duties.tasks.delete'),
    icon: Trash2,
    destructive: true,
    testid: 'btn-delete-task-mobile',
  },
])

const addShiftActions = computed<TaskSheetAction[]>(() => [
  {
    key: 'batch',
    label: t('duties.tasks.detail.addShiftBatch'),
    icon: CalendarPlus,
    testid: 'btn-add-shift-batch-mobile',
  },
  {
    key: 'single',
    label: t('duties.tasks.detail.addSingleShift'),
    icon: Plus,
    testid: 'btn-add-single-shift-mobile',
  },
])

/**
 * The desktop menus run their items through `menu.after`, so a dialog an item
 * opens finds the menu's button focused and hands focus back to it on close.
 */
const menu = useMenuAction()

/**
 * A ⋯ item, from the desktop menu or the phone sheet. The sheet reports a row
 * as it starts to close, so a dialog waits a tick for it to get out of the way.
 */
const onMoreAction = async (key: string) => {
  if (key === 'print') {
    router.push(printRoute.value)
    return
  }
  await nextTick()
  if (key === 'managers') showManagersDialog.value = true
  else if (key === 'vouchers') showVoucherSettings.value = true
  else if (key === 'delete') handleDeleteTask()
}

const onAddShiftAction = async (key: string) => {
  if (key === 'batch') {
    router.push({ name: 'task-add-shifts', params: { eventId: task.value?.id } })
    return
  }
  await nextTick()
  showCreateShiftDialog.value = true
}

/** A place that takes vouchers, and the viewer may take them there right now. */
const canRedeemHere = computed(() => !!task.value?.is_voucher_point && !!task.value?.can_redeem)
/** Always the task's own event, which need not be the selected one. */
const redeemRoute = computed(() => ({
  name: 'voucher-redeem',
  params: { eventId: task.value?.event_id ?? undefined },
  query: { task: task.value?.id },
}))

/**
 * A voucher shift that has begun can no longer be booked by someone who does
 * not run the task (`booking.shift_started`): vouchers are a flat amount per
 * shift, so a late booking would be paid in full.
 */
const startedForVouchers = (shift: ShiftRead) =>
  (task.value?.vouchers_per_shift ?? 0) > 0 &&
  !canManageTask.value &&
  shiftHasStarted(shift.date, shift.start_time)

/**
 * Why a shift that still has places cannot be booked any more, or `null`.
 * Such a tile looks muted like a full one, so "click on a shift to book it"
 * never points at a shift the server would refuse; a click still opens it.
 */
const notBookableNote = (shift: ShiftRead): string | null => {
  if (shiftHasEnded(shift.date, shift.start_time, shift.end_time)) {
    return t('duties.shifts.detail.over')
  }
  if (startedForVouchers(shift)) return t('vouchers.task.startedNote')
  return null
}

const onVoucherSettingsSaved = (saved: TaskRead) => {
  task.value = saved
}

/**
 * The team this task is reserved for, from the task itself: whether the
 * viewer is locked out, and where their own request stands.
 */
const teamGate = computed(() => {
  const tk = task.value
  if (!tk?.team_id || !tk.team_name) return null
  return {
    id: tk.team_id,
    name: tk.team_name,
    locked: !!tk.locked_by_team,
    requiresApproval: tk.team_requires_approval ?? true,
    myStatus: tk.my_team_status ?? null,
  }
})

/** The line under "Duty shifts" while the task is locked. */
const teamPickHint = computed(() => {
  const gate = teamGate.value
  if (!gate?.locked) return null
  if (gate.myStatus === 'pending') return t('teamLocks.gate.pickHintPending', { name: gate.name })
  return gate.requiresApproval
    ? t('teamLocks.gate.pickHintAsk', { name: gate.name })
    : t('teamLocks.gate.pickHint', { name: gate.name })
})

/** Joining (or asking to) changes the lock on the task and every shift. */
const onTeamJoined = () => Promise.all([loadTask({ quiet: true }), loadShifts()])

const task = ref<TaskRead | null>(null)
const shifts = ref<ShiftRead[]>([])
const myBookings = ref<BookingRead[]>([])
const batches = ref<ShiftBatchRead[]>([])
const loading = ref(false)
const showCreateShiftDialog = ref(false)

// Create shift form
const slotForm = ref({
  title: '',
  description: '',
  start_time: '',
  end_time: '',
  location: '',
  location_id: null as string | null,
  category: '',
  max_bookings: 5,
})
const slotDate = ref<DateValue>()

// --- Batch grouping ---
/**
 * Several batches each get a header with their own Edit, which changes that
 * batch's shifts. "Edit task" stays for the task's own details either way; on
 * such a task its edit page leaves the shifts to the batches.
 */
const hasBatches = computed(() => batches.value.length > 1)

interface BatchGroup {
  batch: ShiftBatchRead | null
  shifts: ShiftRead[]
}

const shiftsByBatch = computed<BatchGroup[]>(() => {
  if (!hasBatches.value) {
    // No batches — return all shifts as a single event
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

  // Add batch events in order
  for (const batch of batches.value) {
    const shifts = batchMap.get(batch.id) ?? []
    if (shifts.length > 0) {
      events.push({ batch, shifts })
    }
  }

  // Add unbatched shifts if any
  if (unbatched.length > 0) {
    events.push({ batch: null, shifts: unbatched })
  }

  return events
})

// --- Filters ---
const filterLocation = ref<string | null>(null)
const filterCategory = ref<string | null>(null)

// --- Unique values for filters (only shown when > 1 distinct value) ---
const uniqueLocations = computed(() => {
  const vals = new Set<string>()
  for (const shift of shifts.value) {
    if (shift.location) vals.add(shift.location)
  }
  return [...vals].sort()
})

const uniqueCategories = computed(() => {
  const vals = new Set<string>()
  for (const shift of shifts.value) {
    if (shift.category) vals.add(shift.category)
  }
  return [...vals].sort()
})

const hasMultipleLocations = computed(() => uniqueLocations.value.length > 1)
const hasMultipleCategories = computed(() => uniqueCategories.value.length > 1)
const hasFilters = computed(() => hasMultipleLocations.value || hasMultipleCategories.value)
const isFilterActive = computed(
  () => filterLocation.value !== null || filterCategory.value !== null,
)

// Visible batch events (events with at least one shift matching the filter)
const visibleBatchGroups = computed(() => {
  return shiftsByBatch.value.filter((event) => filterShifts(event.shifts).length > 0)
})

// Count of shifts hidden by the active filter
const hiddenShiftsCount = computed(() => {
  if (!isFilterActive.value) return 0
  return (
    shifts.value.length -
    shifts.value.filter((shift) => {
      if (filterLocation.value && shift.location !== filterLocation.value) return false
      if (filterCategory.value && shift.category !== filterCategory.value) return false
      return true
    }).length
  )
})

// Shared properties (same across all shifts — shown once in header)
const sharedLocation = computed(() => {
  if (uniqueLocations.value.length === 1) return uniqueLocations.value[0]
  return null
})
const sharedCategory = computed(() => {
  if (uniqueCategories.value.length === 1) return uniqueCategories.value[0]
  return null
})

// The one location every shift shares (or the task's own, before it has
// shifts). Only then is "where is it" a single answer worth a mini map.
const sharedLocationId = computed<string | null>(() =>
  sharedLocationIdOf(shifts.value, task.value?.location_id),
)

const sharedLocationDetail = ref<LocationDetailRead | null>(null)
const miniMapPin = computed(() => sharedLocationDetail.value?.pins?.[0] ?? null)
const locationFormOpen = ref(false)

const loadSharedLocation = async () => {
  const id = sharedLocationId.value
  if (!id) {
    sharedLocationDetail.value = null
    return
  }
  try {
    const res = await get<{ data: LocationDetailRead }>({ url: `/locations/${id}` })
    if (sharedLocationId.value === id) sharedLocationDetail.value = res.data
  } catch {
    // Non-critical — the header still shows the name.
    sharedLocationDetail.value = null
  }
}

watch(sharedLocationId, loadSharedLocation)

// A rename rewrites the location text on the task and its shifts. Patched in
// place rather than via `loadTask`, which would blank the page while loading.
const onLocationSaved = async (saved: LocationRead) => {
  if (task.value?.location_id === saved.id) task.value = { ...task.value, location: saved.name }
  await Promise.all([loadShifts(), loadSharedLocation()])
}

// Filter shifts within a event
const filterShifts = (shifts: ShiftRead[]) => {
  return shifts.filter((shift) => {
    if (filterLocation.value && shift.location !== filterLocation.value) return false
    if (filterCategory.value && shift.category !== filterCategory.value) return false
    return true
  })
}

// Group shifts by date (for rendering within a batch event)
const groupByDate = (shifts: ShiftRead[]) => {
  const events: Record<string, ShiftRead[]> = {}
  for (const shift of shifts) {
    const date = shift.date
    if (!events[date]) events[date] = []
    events[date].push(shift)
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

const myBookedShiftIds = computed(() => {
  return new Set(myBookings.value.filter((b) => b.status === 'confirmed').map((b) => b.shift_id))
})

const getBookingForShift = (slotId: string) => {
  return myBookings.value.find((b) => b.shift_id === slotId && b.status === 'confirmed')
}

const isShiftFull = (shift: ShiftRead) => {
  return (shift.current_bookings ?? 0) >= (shift.max_bookings ?? 1)
}

// My booked shifts with full shift details (for summary)
const myBookedShiftsForTask = computed(() => {
  return shifts.value
    .filter((s) => myBookedShiftIds.value.has(s.id))
    .sort(
      (a, b) =>
        a.date.localeCompare(b.date) || (a.start_time ?? '').localeCompare(b.start_time ?? ''),
    )
})

const busyShiftId = ref<string | null>(null)

// Shift detail dialog
const showShiftDetail = ref(false)
const selectedShift = ref<ShiftRead | null>(null)

const openShiftDetail = (shift: ShiftRead) => {
  selectedShift.value = shift
  showShiftDetail.value = true
}

const openBookedShift = (shift: ShiftRead) => {
  const booking = getBookingForShift(shift.id)
  if (booking) {
    router.push({ name: 'booking-detail', params: { bookingId: booking.id } })
  }
}

// --- Delete confirmation dialog with optional reason ---
const showDeleteDialog = ref(false)
const deleteReason = ref('')
const deleteBookingCount = ref(0)
const deleteAction = ref<(() => Promise<void>) | null>(null)
const deleteMessage = ref('')

const openDeleteDialog = (message: string, bookingCount: number, action: () => Promise<void>) => {
  deleteMessage.value = message
  deleteBookingCount.value = bookingCount
  deleteReason.value = ''
  deleteAction.value = action
  showDeleteDialog.value = true
}

const confirmDelete = async () => {
  if (deleteAction.value) {
    showDeleteDialog.value = false
    await deleteAction.value()
  }
}

const countConfirmedBookings = (shifts: ShiftRead[]) => {
  return shifts.reduce((sum, s) => sum + (s.current_bookings ?? 0), 0)
}

const handleShiftClick = async (shift: ShiftRead) => {
  if (busyShiftId.value) return
  busyShiftId.value = shift.id

  try {
    // Over, or a voucher shift already under way: nothing to book or cancel
    // here, so show the shift instead of offering what the server refuses.
    if (
      shiftHasEnded(shift.date, shift.start_time, shift.end_time) ||
      (!myBookedShiftIds.value.has(shift.id) && startedForVouchers(shift))
    ) {
      openShiftDetail(shift)
      return
    }
    if (myBookedShiftIds.value.has(shift.id)) {
      const booking = getBookingForShift(shift.id)
      if (!booking) return
      const confirmed = await confirmDestructive(t('duties.bookings.cancelConfirm'))
      if (!confirmed) return
      await del({ url: `/bookings/${booking.id}` })
      // Optimistic update: decrement count and remove from my bookings
      const idx = shifts.value.findIndex((s) => s.id === shift.id)
      if (idx !== -1) {
        shifts.value[idx].current_bookings = Math.max(
          0,
          (shifts.value[idx].current_bookings ?? 1) - 1,
        )
        shifts.value[idx].is_booked_by_me = false
        shifts.value[idx].bookers = shifts.value[idx].bookers?.filter(
          (b) => b.user_id !== booking.user_id,
        )
      }
      myBookings.value = myBookings.value.filter((b) => b.id !== booking.id)
      toast.success(t('duties.bookings.cancelSuccess'))
      // Freeing this time may lift the clash marker from other shifts.
      void loadShifts()
    } else {
      if (isShiftFull(shift)) return
      if (shift.locked_by_team) {
        // The dialog explains the lock and offers to join the team.
        openShiftDetail(shift)
        return
      }
      if (shift.collides_with_my_booking) {
        toast.error(t('errorCodes.booking.time_conflict'))
        return
      }
      const confirmed = await confirm(t('duties.bookings.bookConfirm'))
      if (!confirmed) return
      const res = await post<{ data: BookingRead }>({
        url: '/bookings/',
        body: { shift_id: shift.id },
      })
      // Optimistic update: increment count and add to my bookings
      const idx = shifts.value.findIndex((s) => s.id === shift.id)
      if (idx !== -1) {
        shifts.value[idx].current_bookings = (shifts.value[idx].current_bookings ?? 0) + 1
        shifts.value[idx].is_booked_by_me = true
        const bookers = shifts.value[idx].bookers
        if (bookers) {
          shifts.value[idx].bookers = [
            ...bookers,
            { user_id: res.data.user_id, name: authStore.profile?.name ?? null },
          ]
        }
      }
      myBookings.value.push({
        ...res.data,
        shift: null,
      } as MyBookingsListResponse['items'][number])
      toast.success(t('duties.bookings.bookSuccess'))
      // The new booking may make other shifts clash with it.
      void loadShifts()
    }
  } catch (error) {
    toastApiError(error)
    // Refetch on error to restore correct state
    await Promise.all([loadShifts(), loadMyBookings()])
  } finally {
    busyShiftId.value = null
  }
}

/**
 * A tap on a shift tile. Whoever runs the task opens it, to see who is on it
 * (and book themselves from there); everyone else books or cancels.
 */
const onShiftSelect = (shift: ShiftRead) => {
  if (canManageTask.value) openShiftDetail(shift)
  else void handleShiftClick(shift)
}

/** Where or what, on each tile, while the task's shifts differ in that. */
const shiftMeta = (shift: ShiftRead): string | null => {
  if (hasBatches.value) return null
  const parts = [
    hasMultipleCategories.value ? shift.category : null,
    hasMultipleLocations.value ? shift.location : null,
  ].filter(Boolean)
  return parts.length ? parts.join(' · ') : null
}

/** The line next to "Shifts": what a tap on a tile does, or how to get in. */
const shiftsHint = computed<string | null>(() => {
  if (shifts.value.length === 0) return null
  if (teamPickHint.value) return teamPickHint.value
  if (canManageTask.value) return isPhone.value ? null : t('duties.tasks.detail.tapToSeeWho')
  if (myBookedShiftsForTask.value.length === 0) return t('duties.tasks.detail.noBookingsYet')
  return null
})

const batchLabel = (batch: ShiftBatchRead) => {
  return batch.label || `${formatDate(batch.start_date)} – ${formatDate(batch.end_date)}`
}

/** Whether the task loaded; on a refusal it has toasted and left for the task list. */
const loadTask = async ({ quiet = false }: { quiet?: boolean } = {}): Promise<boolean> => {
  // A quiet reload keeps the page on screen instead of the loading state.
  if (!quiet) loading.value = true
  try {
    const response = await get<{ data: TaskRead }>({
      url: `/tasks/${eventId.value}`,
    })
    task.value = response.data

    // Set dynamic breadcrumbs
    breadcrumbStore.setBreadcrumbs([
      {
        title: 'Tasks',
        titleKey: 'duties.tasks.title',
        to: { name: 'tasks' },
      },
      {
        title: response.data.name,
      },
    ])
    return true
  } catch (error) {
    toastApiError(error)
    router.push({ name: 'tasks' })
    return false
  } finally {
    loading.value = false
  }
}

const loadShifts = async () => {
  try {
    // With who booked each shift, for the tiles' "2 of 3 · Tomas, Adaeze":
    // one request for the task, not a roster read per tile.
    const response = await get<{ data: ShiftListResponse }>({
      url: '/shifts/',
      query: { task_id: eventId.value, limit: 200, with_bookers: true },
    })
    shifts.value = response.data.items
  } catch (error) {
    toastApiError(error)
  }
}

const loadMyBookings = async () => {
  try {
    const response = await get<{ data: MyBookingsListResponse }>({
      url: '/bookings/me',
      query: { limit: 200 },
    })
    myBookings.value = response.data.items
  } catch (error) {
    toastApiError(error)
  }
}

const loadBatches = async () => {
  try {
    const response = await get<{ data: ShiftBatchRead[] }>({
      url: `/tasks/${eventId.value}/batches`,
    })
    batches.value = response.data
  } catch {
    // Non-critical — older tasks may not have batches
  }
}

const handleStatusChange = async (status: 'draft' | 'published' | 'archived') => {
  if (!task.value || task.value.status === status) return
  try {
    const response = await patch<{ data: TaskRead }>({
      url: `/tasks/${task.value.id}`,
      body: { status },
    })
    task.value = response.data
    toast.success(t(`duties.tasks.statuses.${status}`))
    // The event's voucher counts follow published tasks only.
    const tk = response.data
    if (tk.event_id && ((tk.vouchers_per_shift ?? 0) > 0 || tk.is_voucher_point)) {
      void authStore.refreshSelectedEvent(tk.event_id)
    }
  } catch (error) {
    toastApiError(error)
  }
}

/** Naming or removing someone changes `managers` and maybe `can_manage`. */
const onManagersChanged = () =>
  Promise.all([loadTask({ quiet: true }), inChargeCard.value?.reloadInvitations()])

/** A person in charge gives the task back to the organisers. */
const handleStepDown = async () => {
  const tk = task.value
  const me = authStore.profile?.id
  if (!tk || !me) return
  const others = (tk.managers ?? []).filter((m) => m.user_id !== me).map((m) => m.name || '?')
  const text = [
    t('duties.tasks.managers.stepDownText', { task: tk.name }),
    others.length
      ? t(
          'duties.tasks.managers.stepDownOthers',
          { names: joinNames(others, locale.value) },
          others.length,
        )
      : t('duties.tasks.managers.stepDownNobody'),
    // Unpublished, the task drops out of sight as well; say so before it does.
    tk.status === 'published'
      ? t('duties.tasks.managers.stepDownBookings')
      : t('duties.tasks.managers.stepDownHidden'),
  ].join(' ')
  const ok = await confirmDestructive({
    title: t('duties.tasks.managers.stepDownTitle'),
    text,
    confirmText: t('duties.tasks.managers.stepDownYes'),
  })
  if (!ok) return
  try {
    await del({ url: `/tasks/${tk.id}/managers/${me}` })
    toast.success(t('duties.tasks.managers.steppedDown'))
  } catch (error) {
    toastApiError(error)
    return
  }
  // An unpublished task is out of reach now: reloading it would answer
  // `task.not_published` and toast an error on the way out.
  if (tk.status === 'published') await loadTask({ quiet: true })
  else router.push({ name: 'tasks' })
}

const handleDeleteTask = () => {
  const bookingCount = countConfirmedBookings(shifts.value)
  openDeleteDialog(t('duties.tasks.deleteConfirm'), bookingCount, async () => {
    try {
      const query: Record<string, string> = {}
      if (deleteReason.value.trim()) query.cancellation_reason = deleteReason.value.trim()
      await del({ url: `/tasks/${eventId.value}`, query })
      toast.success(t('duties.tasks.delete'))
      router.push({ name: 'tasks' })
    } catch (error) {
      toastApiError(error)
    }
  })
}

const handleDeleteBatch = (batch: ShiftBatchRead) => {
  const batchShifts = shifts.value.filter((s) => s.batch_id === batch.id)
  const bookingCount = countConfirmedBookings(batchShifts)
  openDeleteDialog(t('duties.tasks.detail.deleteBatchConfirm'), bookingCount, async () => {
    try {
      const query: Record<string, string> = {}
      if (deleteReason.value.trim()) query.cancellation_reason = deleteReason.value.trim()
      await del({ url: `/tasks/${eventId.value}/batches/${batch.id}`, query })
      toast.success(t('duties.tasks.detail.deleteBatchSuccess'))
      await Promise.all([loadShifts(), loadBatches()])
    } catch (error) {
      toastApiError(error)
    }
  })
}

const handleCreateShift = async () => {
  if (!slotDate.value) return
  try {
    await post({
      url: '/shifts/',
      body: {
        task_id: eventId.value,
        title: slotForm.value.title,
        description: slotForm.value.description || undefined,
        date: slotDate.value.toString(),
        start_time: slotForm.value.start_time || undefined,
        end_time: slotForm.value.end_time || undefined,
        location_id: slotForm.value.location_id,
        location: slotForm.value.location || undefined,
        category: slotForm.value.category || undefined,
        max_bookings: slotForm.value.max_bookings,
      },
    })
    showCreateShiftDialog.value = false
    slotForm.value = {
      title: '',
      description: '',
      start_time: '',
      end_time: '',
      location: '',
      location_id: null,
      category: '',
      max_bookings: 5,
    }
    slotDate.value = undefined
    toast.success(t('duties.shifts.created'))
    await loadShifts()
  } catch (error) {
    toastApiError(error)
  }
}

const handleDeleteShift = (shift: ShiftRead) => {
  const bookingCount = shift.current_bookings ?? 0
  openDeleteDialog(t('duties.shifts.deleteConfirm'), bookingCount, async () => {
    try {
      const query: Record<string, string> = {}
      if (deleteReason.value.trim()) query.cancellation_reason = deleteReason.value.trim()
      await del({ url: `/shifts/${shift.id}`, query })
      toast.success(t('duties.shifts.deleted'))
      await loadShifts()
    } catch (error) {
      toastApiError(error)
    }
  })
}

const reloadShiftsAndBookings = () => Promise.all([loadShifts(), loadMyBookings()])

onMounted(async () => {
  // A refused task has already been reported; its shifts would only be
  // refused again, with a second identical toast.
  if (!(await loadTask())) return
  await Promise.all([loadShifts(), loadMyBookings(), loadBatches()])
})
</script>

<template>
  <div class="mx-auto max-w-[70rem]">
    <!-- Loading -->
    <div v-if="loading" class="text-center py-12 text-muted-foreground">
      {{ t('common.states.loading') }}
    </div>

    <div v-else-if="task" class="flex flex-col gap-5 md:gap-7">
      <RouterLink
        data-testid="btn-back"
        :to="{ name: 'tasks' }"
        class="-mb-2 flex min-h-8 items-center gap-1.5 self-start rounded-md text-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50 max-xl:hidden"
      >
        <ArrowLeft class="size-4" aria-hidden="true" />
        {{ t('duties.tasks.title') }}
      </RouterLink>

      <!-- Header: name and status, what and where, the actions -->
      <header class="flex flex-wrap items-start justify-between gap-x-5 gap-y-3">
        <div class="flex min-w-0 flex-1 basis-[32rem] flex-col gap-2.5 md:gap-2">
          <div class="flex items-start gap-2">
            <div class="flex min-w-0 flex-1 flex-wrap items-center gap-x-2.5 gap-y-1.5 md:gap-x-3">
              <h1
                data-testid="page-heading"
                class="text-[26px] leading-tight font-bold tracking-[-0.01em] break-words md:text-[32px] md:leading-[1.15] md:tracking-[-0.015em]"
              >
                {{ task.name }}
              </h1>
              <StatusDropdown
                data-testid="task-status"
                pill
                :status="task.status"
                i18n-prefix="duties.tasks.statuses"
                :editable="canAdminEvent"
                @change="handleStatusChange"
              />
            </div>
            <template v-if="isPhone">
              <Button
                v-if="canAdminEvent"
                data-testid="btn-task-more"
                variant="outline"
                size="icon"
                class="size-11 shrink-0 rounded-xl shadow-none"
                :aria-label="t('common.actions.moreActions')"
                @click="moreSheetOpen = true"
              >
                <Ellipsis class="size-[18px]" />
              </Button>
              <Button
                v-else
                data-testid="btn-print"
                variant="outline"
                size="icon"
                class="size-11 shrink-0 rounded-xl shadow-none"
                :aria-label="t('print.printTask')"
                @click="router.push(printRoute)"
              >
                <Printer class="size-[18px]" />
              </Button>
            </template>
          </div>

          <p
            v-if="task.description"
            class="line-clamp-3 max-w-[40rem] text-[15px] break-words text-foreground/80 md:text-base"
          >
            {{ task.description }}
          </p>

          <div
            class="flex flex-wrap items-center gap-x-3.5 gap-y-1 text-sm text-muted-foreground md:gap-x-[18px] md:gap-y-1.5"
          >
            <span v-if="daySpan" class="flex items-center gap-1.5">
              <CalendarDays class="size-[15px] shrink-0 md:size-4" aria-hidden="true" />
              {{ daySpan }}
            </span>
            <span v-if="sharedLocation" class="flex max-w-xs min-w-0 items-center gap-1.5">
              <MapPin class="size-[15px] shrink-0 md:size-4" aria-hidden="true" />
              <span class="truncate">{{ sharedLocation }}</span>
            </span>
            <span v-if="sharedCategory" class="flex max-w-xs min-w-0 items-center gap-1.5">
              <Tag class="size-[15px] shrink-0 md:size-4" aria-hidden="true" />
              <span class="truncate">{{ sharedCategory }}</span>
            </span>
            <span
              v-if="!isPhone"
              class="flex max-w-xs min-w-0 items-center gap-1.5"
              data-testid="task-audience"
            >
              <UsersRound class="size-4 shrink-0" aria-hidden="true" />
              <span class="truncate">{{ audience }}</span>
            </span>
          </div>

          <EventZoneHint :zone="task.event_timezone" />

          <!-- A draft, said calmly: who can't see it yet and who can change that -->
          <p
            v-if="task.status === 'draft'"
            class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm text-muted-foreground"
            data-testid="task-draft-banner"
          >
            <EyeOff
              class="size-4 shrink-0 self-start max-md:mt-0.5 md:self-center"
              aria-hidden="true"
            />
            <span class="min-w-0 flex-1 md:flex-none">
              {{
                canAdminEvent
                  ? t('duties.tasks.detail.draftLine')
                  : t('duties.tasks.detail.draftLineManager')
              }}
            </span>
            <button
              v-if="canAdminEvent && !isPhone"
              type="button"
              class="min-h-8 rounded-md px-1 font-bold text-primary underline underline-offset-[3px] outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
              data-testid="btn-publish-now"
              @click="handleStatusChange('published')"
            >
              {{ t('duties.tasks.detail.publishNow') }}
            </button>
          </p>

          <!-- Phone actions, under the details and within reach -->
          <div v-if="isPhone && canManageTask" class="mt-1 flex gap-2">
            <template v-if="canManageShifts">
              <Button
                data-testid="btn-add-shifts"
                class="h-12 min-w-0 flex-1 rounded-xl text-[15px] font-bold"
                @click="addShiftsSheetOpen = true"
              >
                <CalendarPlus class="size-[18px]" />
                {{ t('duties.tasks.detail.addShifts') }}
              </Button>
              <Button
                data-testid="btn-edit-task"
                variant="outline"
                class="h-12 shrink-0 rounded-xl px-4 text-[15px] font-semibold shadow-none"
                @click="router.push({ name: 'task-edit', params: { eventId: task.id } })"
              >
                <Pencil />
                {{ t('common.actions.edit') }}
              </Button>
            </template>
            <Button
              v-else
              data-testid="btn-edit-task"
              variant="outline"
              class="h-12 w-full rounded-xl text-[15px] font-semibold shadow-none"
              @click="router.push({ name: 'task-edit', params: { eventId: task.id } })"
            >
              <Pencil />
              {{ t('duties.tasks.edit') }}
            </Button>
          </div>
        </div>

        <!-- Desktop actions -->
        <div v-if="!isPhone" class="flex shrink-0 items-center gap-2">
          <template v-if="canAdminEvent">
            <Button
              data-testid="btn-edit-task"
              variant="outline"
              class="h-11 rounded-xl px-4 font-semibold shadow-none"
              @click="router.push({ name: 'task-edit', params: { eventId: task.id } })"
            >
              <Pencil />
              {{ t('common.actions.edit') }}
            </Button>
            <DropdownMenu v-if="canManageShifts">
              <DropdownMenuTrigger as-child>
                <Button data-testid="btn-add-shifts" class="h-11 rounded-xl pr-3 pl-4 font-bold">
                  <CalendarPlus />
                  {{ t('duties.tasks.detail.addShifts') }}
                  <ChevronDown />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                class="rounded-[14px] p-1.5"
                @close-auto-focus="menu.onCloseAutoFocus"
              >
                <DropdownMenuItem
                  class="min-h-[42px] gap-2.5 rounded-[10px] px-2.5"
                  @select="onAddShiftAction('batch')"
                >
                  <CalendarPlus />
                  {{ t('duties.tasks.detail.addShiftBatch') }}
                </DropdownMenuItem>
                <DropdownMenuItem
                  data-testid="btn-add-single-shift"
                  class="min-h-[42px] gap-2.5 rounded-[10px] px-2.5"
                  @select="menu.after(() => onAddShiftAction('single'))"
                >
                  <Plus />
                  {{ t('duties.tasks.detail.addSingleShift') }}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <DropdownMenu>
              <DropdownMenuTrigger as-child>
                <Button
                  data-testid="btn-task-more"
                  variant="outline"
                  size="icon"
                  class="size-11 rounded-xl shadow-none data-[state=open]:bg-muted"
                  :aria-label="t('common.actions.moreActions')"
                >
                  <Ellipsis class="size-[18px]" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                class="w-[272px] rounded-[14px] p-1.5"
                @close-auto-focus="menu.onCloseAutoFocus"
              >
                <DropdownMenuItem
                  data-testid="btn-task-managers"
                  class="min-h-[42px] gap-2.5 rounded-[10px] px-2.5"
                  @select="menu.after(() => onMoreAction('managers'))"
                >
                  <UsersRound />
                  {{ t('duties.tasks.managers.manage') }}
                </DropdownMenuItem>
                <DropdownMenuItem
                  data-testid="btn-task-vouchers"
                  class="min-h-[42px] gap-2.5 rounded-[10px] px-2.5"
                  @select="menu.after(() => onMoreAction('vouchers'))"
                >
                  <Ticket />
                  {{ t('vouchers.settings.open') }}
                </DropdownMenuItem>
                <DropdownMenuItem
                  data-testid="btn-print"
                  class="min-h-[42px] gap-2.5 rounded-[10px] px-2.5"
                  @select="onMoreAction('print')"
                >
                  <Printer />
                  {{ t('duties.tasks.detail.print') }}
                </DropdownMenuItem>
                <DropdownMenuSeparator class="mx-1 my-1.5" />
                <DropdownMenuItem
                  data-testid="btn-delete-task"
                  class="min-h-[42px] gap-2.5 rounded-[10px] px-2.5 text-destructive focus:text-destructive"
                  @select="menu.after(() => onMoreAction('delete'))"
                >
                  <Trash2 class="text-destructive" />
                  {{ t('duties.tasks.delete') }}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </template>

          <template v-else>
            <HintTooltip :label="t('print.printTask')">
              <Button
                data-testid="btn-print"
                variant="outline"
                size="icon"
                class="size-11 rounded-xl shadow-none"
                :aria-label="t('print.printTask')"
                @click="router.push(printRoute)"
              >
                <Printer class="size-[18px]" />
              </Button>
            </HintTooltip>
            <DropdownMenu v-if="canManageShifts">
              <DropdownMenuTrigger as-child>
                <Button
                  data-testid="btn-add-shifts"
                  variant="outline"
                  class="h-11 rounded-xl pr-3 pl-4 font-semibold shadow-none"
                >
                  <CalendarPlus />
                  {{ t('duties.tasks.detail.addShifts') }}
                  <ChevronDown />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                class="rounded-[14px] p-1.5"
                @close-auto-focus="menu.onCloseAutoFocus"
              >
                <DropdownMenuItem
                  class="min-h-[42px] gap-2.5 rounded-[10px] px-2.5"
                  @select="onAddShiftAction('batch')"
                >
                  <CalendarPlus />
                  {{ t('duties.tasks.detail.addShiftBatch') }}
                </DropdownMenuItem>
                <DropdownMenuItem
                  data-testid="btn-add-single-shift"
                  class="min-h-[42px] gap-2.5 rounded-[10px] px-2.5"
                  @select="menu.after(() => onAddShiftAction('single'))"
                >
                  <Plus />
                  {{ t('duties.tasks.detail.addSingleShift') }}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <Button
              v-if="canManageTask"
              data-testid="btn-edit-task"
              class="h-11 rounded-xl px-[18px] font-bold"
              @click="router.push({ name: 'task-edit', params: { eventId: task.id } })"
            >
              <Pencil />
              {{ t('duties.tasks.edit') }}
            </Button>
          </template>
        </div>
      </header>

      <!-- Reserved for one team: who can book, and joining in place -->
      <Alert
        v-if="teamGate"
        data-testid="task-team-gate"
        class="rounded-2xl"
        :class="teamGate.locked ? 'bg-muted/40' : ''"
      >
        <Lock class="h-4 w-4" />
        <AlertDescription
          class="flex flex-col gap-3 text-foreground sm:flex-row sm:items-center sm:justify-between"
        >
          <I18nT
            :keypath="
              !teamGate.locked
                ? teamGate.myStatus === 'approved'
                  ? 'teamLocks.gate.member'
                  : 'teamLocks.gate.manager'
                : teamGate.myStatus === 'pending'
                  ? 'teamLocks.gate.pending'
                  : 'teamLocks.gate.locked'
            "
            tag="span"
            scope="global"
          >
            <template #name>
              <strong class="font-semibold">{{ teamGate.name }}</strong>
            </template>
          </I18nT>
          <TeamJoinButton
            v-if="teamGate.locked"
            :event-id="task.event_id"
            :team-id="teamGate.id"
            :team-name="teamGate.name"
            :requires-approval="teamGate.requiresApproval"
            :my-status="teamGate.myStatus"
            class="shrink-0 max-sm:w-full"
            @joined="onTeamJoined"
          />
        </AlertDescription>
      </Alert>

      <!-- Who runs it, and how vouchers work here -->
      <div
        v-if="showInChargeCard || showVouchersCard"
        class="grid items-stretch gap-3.5 md:grid-cols-2 md:gap-5"
      >
        <TaskInChargeCard
          v-if="showInChargeCard"
          ref="inChargeCard"
          :task="task"
          :can-admin="canAdminEvent"
          :my-id="myId"
          :in-charge="isManagerOnly"
          :shifts-locked="shiftsLocked"
          :compact="isPhone"
          @manage="showManagersDialog = true"
          @step-down="handleStepDown"
        />
        <TaskVouchersCard
          v-if="showVouchersCard"
          class="max-md:order-first"
          :task="task"
          :can-admin="canAdminEvent"
          :can-manage="canManageTask"
          :can-redeem="canRedeemHere"
          :redeem-to="redeemRoute"
          :compact="isPhone"
          @settings="showVoucherSettings = true"
        />
      </div>

      <!-- Where it happens: mini map of the shared location -->
      <div
        v-if="sharedLocationDetail && (miniMapPin || canAdminEvent)"
        class="space-y-1.5 sm:max-w-md"
        data-testid="task-mini-map"
      >
        <VenueMiniMap
          v-if="miniMapPin"
          :event-id="sharedLocationDetail.event_id"
          :pin="miniMapPin"
          :location-id="sharedLocationDetail.id"
        />
        <Button
          v-if="canAdminEvent"
          variant="link"
          size="sm"
          class="h-auto px-0"
          data-testid="btn-task-location-details"
          @click="locationFormOpen = true"
        >
          <MapPin class="mr-1 h-3.5 w-3.5" />
          {{ t('locations.details.openForm') }}
        </Button>
      </div>

      <!-- My Bookings Summary -->
      <Transition
        enter-active-class="grid transition-[grid-template-rows,opacity] duration-300 ease-out"
        enter-from-class="grid-rows-[0fr] opacity-0"
        enter-to-class="grid-rows-[1fr] opacity-100"
        leave-active-class="grid transition-[grid-template-rows,opacity] duration-200 ease-in"
        leave-from-class="grid-rows-[1fr] opacity-100"
        leave-to-class="grid-rows-[0fr] opacity-0"
      >
        <div v-if="myBookedShiftsForTask.length > 0">
          <div class="overflow-hidden space-y-3">
            <div class="flex items-center gap-2">
              <CalendarCheck class="h-5 w-5 text-primary" />
              <h2 class="text-lg font-bold">{{ t('duties.tasks.detail.myBookings') }}</h2>
              <Badge variant="default" class="rounded-full">
                {{
                  t('duties.tasks.detail.myBookingsCount', { count: myBookedShiftsForTask.length })
                }}
              </Badge>
            </div>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="shift in myBookedShiftsForTask"
                :key="shift.id"
                type="button"
                class="min-h-9 rounded-full bg-secondary px-3 py-1.5 text-sm font-medium text-secondary-foreground transition-colors outline-none hover:bg-secondary/80 hover:ring-1 hover:ring-primary/30 focus-visible:ring-[3px] focus-visible:ring-ring/50"
                @click="openBookedShift(shift)"
              >
                {{ formatDateLabel(shift.date) }}
                <template v-if="shift.start_time">
                  &middot; {{ formatTime(shift.start_time)
                  }}<template v-if="shift.end_time"> - {{ formatTime(shift.end_time) }}</template>
                </template>
                <template v-if="hasMultipleLocations && shift.location">
                  &middot; {{ shift.location }}</template
                >
                <template v-if="hasMultipleCategories && shift.category">
                  &middot; {{ shift.category }}</template
                >
              </button>
            </div>
          </div>
        </div>
      </Transition>

      <!-- Shifts -->
      <section
        data-testid="section-shifts"
        aria-labelledby="task-shifts-title"
        class="flex flex-col gap-2.5 max-md:mt-1.5 md:gap-3.5"
      >
        <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 id="task-shifts-title" class="text-lg font-bold md:text-xl">
            {{ t('duties.tasks.detail.shifts') }}
          </h2>
          <p
            v-if="shiftsHint"
            class="text-sm text-muted-foreground"
            :data-testid="teamPickHint ? 'task-team-pick-hint' : 'task-shifts-hint'"
          >
            {{ shiftsHint }}
          </p>
        </div>

        <!-- Filters (only shown when multiple distinct values exist) -->
        <div v-if="hasFilters" class="flex flex-wrap gap-3">
          <!-- Location filter -->
          <div v-if="hasMultipleLocations" class="flex flex-wrap items-center gap-1.5">
            <MapPin class="h-4 w-4 text-muted-foreground" />
            <button
              class="min-h-8 rounded-full border px-3 py-1 text-sm transition-colors"
              :class="
                filterLocation === null
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-card hover:bg-muted'
              "
              @click="filterLocation = null"
            >
              {{ t('duties.tasks.detail.allLocations') }}
            </button>
            <button
              v-for="loc in uniqueLocations"
              :key="loc"
              class="min-h-8 rounded-full border px-3 py-1 text-sm transition-colors"
              :class="
                filterLocation === loc
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-card hover:bg-muted'
              "
              @click="filterLocation = loc"
            >
              {{ loc }}
            </button>
          </div>

          <!-- Category filter -->
          <div v-if="hasMultipleCategories" class="flex flex-wrap items-center gap-1.5">
            <Tag class="h-4 w-4 text-muted-foreground" />
            <button
              class="min-h-8 rounded-full border px-3 py-1 text-sm transition-colors"
              :class="
                filterCategory === null
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-card hover:bg-muted'
              "
              @click="filterCategory = null"
            >
              {{ t('duties.tasks.detail.allCategories') }}
            </button>
            <button
              v-for="cat in uniqueCategories"
              :key="cat"
              class="min-h-8 rounded-full border px-3 py-1 text-sm transition-colors"
              :class="
                filterCategory === cat
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-card hover:bg-muted'
              "
              @click="filterCategory = cat"
            >
              {{ cat }}
            </button>
          </div>
        </div>

        <div v-if="shifts.length === 0" class="text-center py-8 text-muted-foreground">
          {{ t('duties.shifts.empty') }}
        </div>

        <!-- Batch-grouped shifts -->
        <div v-else class="flex flex-col gap-6">
          <template
            v-for="(event, eventIdx) in visibleBatchGroups"
            :key="event.batch?.id ?? 'unbatched'"
          >
            <div class="flex flex-col gap-3">
              <!-- Batch header (only when there are multiple batches) -->
              <div v-if="hasBatches" class="flex items-center justify-between gap-2">
                <div class="flex min-w-0 flex-wrap items-center gap-2">
                  <h3 class="text-base font-bold md:text-lg">
                    {{
                      event.batch
                        ? batchLabel(event.batch)
                        : t('duties.tasks.detail.unbatchedShifts')
                    }}
                  </h3>
                  <span
                    class="rounded-full bg-secondary px-2 py-px text-xs font-semibold text-secondary-foreground"
                  >
                    {{
                      t(
                        'duties.tasks.detail.shiftsCount',
                        { count: filterShifts(event.shifts).length },
                        filterShifts(event.shifts).length,
                      )
                    }}
                  </span>
                  <template v-if="event.batch">
                    <Badge v-if="event.batch.location" variant="secondary" class="text-xs">
                      <MapPin class="mr-1 h-3 w-3" />
                      {{ event.batch.location }}
                    </Badge>
                    <Badge v-if="event.batch.category" variant="outline" class="text-xs">
                      <Tag class="mr-1 h-3 w-3" />
                      {{ event.batch.category }}
                    </Badge>
                  </template>
                </div>
                <div v-if="canManageShifts && event.batch" class="flex shrink-0 gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    class="max-md:h-11"
                    :aria-label="t('duties.tasks.editView.editBatch')"
                    data-testid="btn-edit-batch"
                    @click="
                      router.push({
                        name: 'task-edit',
                        params: { eventId: task!.id },
                        query: { batchId: event.batch!.id },
                      })
                    "
                  >
                    <Pencil class="mr-1.5 h-3.5 w-3.5" />
                    {{ t('common.actions.edit') }}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    class="text-destructive hover:text-destructive max-md:size-11"
                    :aria-label="t('duties.tasks.detail.deleteBatch')"
                    data-testid="btn-delete-batch"
                    @click="handleDeleteBatch(event.batch!)"
                  >
                    <Trash2 class="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>

              <!-- Shifts grouped by date within this batch -->
              <div
                v-for="[date, dayShifts] in groupByDate(filterShifts(event.shifts))"
                :key="date"
                class="flex flex-col gap-2 md:gap-2.5"
              >
                <h3 class="mt-1.5 flex items-center gap-2 text-sm font-bold">
                  {{ dayLabel(date) }}
                  <span
                    class="rounded-full bg-secondary px-2 py-px text-xs font-semibold text-secondary-foreground"
                  >
                    {{
                      t(
                        'duties.tasks.detail.shiftsCount',
                        { count: dayShifts.length },
                        dayShifts.length,
                      )
                    }}
                  </span>
                </h3>
                <div
                  class="grid grid-cols-2 gap-2 md:grid-cols-[repeat(auto-fill,minmax(220px,1fr))] md:gap-3"
                >
                  <TaskShiftTile
                    v-for="shift in dayShifts"
                    :key="shift.id"
                    :shift="shift"
                    :mine="myBookedShiftIds.has(shift.id)"
                    :busy="busyShiftId === shift.id"
                    :manage="canManageTask"
                    :note="notBookableNote(shift)"
                    :can-delete="canManageShifts"
                    :meta="shiftMeta(shift)"
                    :compact="isPhone"
                    @select="onShiftSelect(shift)"
                    @details="openShiftDetail(shift)"
                    @delete="handleDeleteShift(shift)"
                  />
                </div>
              </div>

              <!-- Separator between batch events -->
              <Separator v-if="hasBatches && eventIdx < visibleBatchGroups.length - 1" />
            </div>
          </template>

          <!-- Hidden shifts info -->
          <p v-if="hiddenShiftsCount > 0" class="text-sm text-muted-foreground text-center py-2">
            {{ t('duties.tasks.detail.hiddenShifts', { count: hiddenShiftsCount }) }}
          </p>
        </div>
      </section>
    </div>

    <!-- Phone sheets -->
    <TaskActionSheet
      v-if="task && isPhone && canAdminEvent"
      v-model:open="moreSheetOpen"
      :title="task.name"
      :description="t('common.actions.moreActions')"
      :actions="moreActions"
      testid="task-more-sheet"
      @select="onMoreAction"
    />
    <TaskActionSheet
      v-if="task && isPhone && canManageShifts"
      v-model:open="addShiftsSheetOpen"
      :title="t('duties.tasks.detail.addShifts')"
      :actions="addShiftActions"
      testid="task-add-shifts-sheet"
      @select="onAddShiftAction"
    />

    <!-- Delete Confirmation Dialog -->
    <DeleteConfirmationDialog
      v-model:open="showDeleteDialog"
      v-model:reason="deleteReason"
      :message="deleteMessage"
      :booking-count="deleteBookingCount"
      @confirm="confirmDelete"
    />

    <!-- Create Shift Dialog -->
    <ResponsiveDialog v-model:open="showCreateShiftDialog">
      <ResponsiveDialogContent data-testid="dialog-create-shift">
        <ResponsiveDialogHeader>
          <ResponsiveDialogTitle>{{ t('duties.shifts.create') }}</ResponsiveDialogTitle>
          <ResponsiveDialogDescription>{{
            t('duties.tasks.detail.addShift')
          }}</ResponsiveDialogDescription>
        </ResponsiveDialogHeader>
        <form class="contents" @submit.prevent="handleCreateShift">
          <ResponsiveDialogBody class="space-y-4 pb-2">
            <div class="space-y-2">
              <Label>{{ t('duties.shifts.fields.title') }}</Label>
              <Input v-model="slotForm.title" data-testid="input-shift-title" required />
            </div>
            <div class="space-y-2">
              <Label>{{ t('duties.shifts.fields.description') }}</Label>
              <Input v-model="slotForm.description" />
            </div>
            <div class="space-y-2">
              <Label>{{ t('duties.shifts.fields.date') }}</Label>
              <DatePicker v-model="slotDate" :placeholder="t('duties.shifts.pickDate')" />
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div class="space-y-2">
                <Label>{{ t('duties.shifts.fields.startTime') }}</Label>
                <TimePicker v-model="slotForm.start_time" />
              </div>
              <div class="space-y-2">
                <Label>{{ t('duties.shifts.fields.endTime') }}</Label>
                <TimePicker v-model="slotForm.end_time" />
              </div>
            </div>
            <div class="grid items-start gap-4 sm:grid-cols-2">
              <div class="space-y-2">
                <Label for="shift-location">{{ t('duties.shifts.fields.location') }}</Label>
                <LocationPicker
                  v-model:location-id="slotForm.location_id"
                  v-model:text="slotForm.location"
                  :event-id="task?.event_id"
                  input-id="shift-location"
                  priority
                />
              </div>
              <div class="space-y-2">
                <Label>{{ t('duties.shifts.fields.category') }}</Label>
                <Input v-model="slotForm.category" />
              </div>
            </div>
            <div class="space-y-2">
              <Label>{{ t('duties.shifts.fields.maxBookings') }}</Label>
              <Input v-model.number="slotForm.max_bookings" type="number" min="1" required />
            </div>
          </ResponsiveDialogBody>
          <ResponsiveDialogFooter>
            <Button type="button" variant="outline" @click="showCreateShiftDialog = false">
              {{ t('common.actions.cancel') }}
            </Button>
            <Button type="submit" data-testid="btn-create-shift">{{
              t('common.actions.create')
            }}</Button>
          </ResponsiveDialogFooter>
        </form>
      </ResponsiveDialogContent>
    </ResponsiveDialog>

    <LocationFormDialog
      v-if="sharedLocationDetail && task?.event_id && canAdminEvent"
      v-model:open="locationFormOpen"
      :event-id="task.event_id"
      :location="sharedLocationDetail"
      @saved="onLocationSaved"
    />

    <TaskManagersDialog
      v-if="task && canAdminEvent"
      v-model:open="showManagersDialog"
      :task="task"
      :reload="onManagersChanged"
    />

    <TaskVoucherSettingsDialog
      v-if="task && canAdminEvent"
      v-model:open="showVoucherSettings"
      :task="task"
      @saved="onVoucherSettingsSaved"
    />

    <!-- Shift Detail Dialog -->
    <ShiftDetailDialog
      v-model:open="showShiftDetail"
      :shift="selectedShift"
      :task-name="task?.name"
      :show-task-link="false"
      :vouchers-per-shift="task?.vouchers_per_shift ?? 0"
      :can-manage-task="canManageTask"
      :managers="task?.managers ?? []"
      :my-booking="selectedShift ? (getBookingForShift(selectedShift.id) ?? null) : null"
      @booking-updated="reloadShiftsAndBookings"
      @team-joined="onTeamJoined"
    />
  </div>
</template>
