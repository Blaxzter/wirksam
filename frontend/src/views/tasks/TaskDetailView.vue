<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import type { DateValue } from '@internationalized/date'
import {
  ArrowLeft,
  CalendarCheck,
  CalendarPlus,
  CalendarX2,
  Check,
  ChevronDown,
  EllipsisVertical,
  Expand,
  Info,
  Lock,
  MapPin,
  Pencil,
  Plus,
  Printer,
  Tag,
  Trash2,
} from '@lucide/vue'
import { I18nT, useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'
import { useBreadcrumbStore } from '@/stores/breadcrumb'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'
import { useFormatters } from '@/composables/useFormatters'

import { Alert, AlertDescription } from '@/components/ui/alert'
import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent } from '@/components/ui/card'
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

import LocationFormDialog from '@/components/locations/LocationFormDialog.vue'
import LocationPicker from '@/components/locations/LocationPicker.vue'
import DeleteConfirmationDialog from '@/components/tasks/DeleteConfirmationDialog.vue'
import ShiftDetailDialog from '@/components/tasks/ShiftDetailDialog.vue'
import StatusDropdown from '@/components/tasks/StatusDropdown.vue'
import TeamJoinButton from '@/components/tasks/TeamJoinButton.vue'
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
import { sharedLocationId as sharedLocationIdOf } from '@/lib/venue-map'

const { t } = useI18n()
const { formatTime, formatDateLabel } = useFormatters()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const breadcrumbStore = useBreadcrumbStore()
const { get, post, patch, delete: del } = useAuthenticatedClient()
const { confirm, confirmDestructive } = useDialog()

const eventId = computed(() => route.params.eventId as string)

const canManage = computed(() => authStore.canManageEvent(task.value?.event_id))

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

const batchLabel = (batch: ShiftBatchRead) => {
  return batch.label || `${formatDate(batch.start_date)} – ${formatDate(batch.end_date)}`
}

const loadTask = async ({ quiet = false }: { quiet?: boolean } = {}) => {
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
  } catch (error) {
    toastApiError(error)
    router.push({ name: 'tasks' })
  } finally {
    loading.value = false
  }
}

const loadShifts = async () => {
  try {
    const response = await get<{ data: ShiftListResponse }>({
      url: '/shifts/',
      query: { task_id: eventId.value, limit: 200 },
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
  } catch (error) {
    toastApiError(error)
  }
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
    toast.success(t('duties.shifts.create'))
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
      toast.success(t('duties.shifts.delete'))
      await loadShifts()
    } catch (error) {
      toastApiError(error)
    }
  })
}

const reloadShiftsAndBookings = () => Promise.all([loadShifts(), loadMyBookings()])

onMounted(async () => {
  await loadTask()
  await Promise.all([loadShifts(), loadMyBookings(), loadBatches()])
})
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <!-- Loading -->
    <div v-if="loading" class="text-center py-12 text-muted-foreground">
      {{ t('common.states.loading') }}
    </div>

    <template v-else-if="task">
      <!-- Back button + Header -->
      <div class="space-y-4">
        <Button
          data-testid="btn-back"
          variant="ghost"
          size="sm"
          class="max-xl:hidden"
          @click="router.push({ name: 'tasks' })"
        >
          <ArrowLeft class="mr-2 h-4 w-4" />
          {{ t('common.actions.back') }}
        </Button>

        <!-- Draft banner -->
        <Alert
          v-if="task.status === 'draft'"
          variant="default"
          class="border-amber-500/50 bg-amber-50 text-amber-900 dark:bg-amber-950/30 dark:text-amber-200 dark:border-amber-500/30"
        >
          <Info class="h-4 w-4 text-amber-600 dark:text-amber-400" />
          <AlertDescription>
            {{ t('duties.tasks.draftBanner') }}
          </AlertDescription>
        </Alert>

        <!-- Reserved for one team: who can book, and joining in place -->
        <Alert
          v-if="teamGate"
          data-testid="task-team-gate"
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

        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0 flex-1 space-y-2">
            <div class="flex items-center gap-3 flex-wrap">
              <h1
                data-testid="page-heading"
                class="text-2xl sm:text-3xl font-bold line-clamp-2 break-words"
              >
                {{ task.name }}
              </h1>
              <StatusDropdown
                data-testid="task-status"
                :status="task.status"
                i18n-prefix="duties.tasks.statuses"
                :editable="canManage"
                @change="handleStatusChange"
              />
            </div>
            <p v-if="task.description" class="text-muted-foreground line-clamp-3 break-words">
              {{ task.description }}
            </p>
            <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
              <span>{{ formatDate(task.start_date) }} - {{ formatDate(task.end_date) }}</span>
              <span v-if="sharedLocation" class="flex items-center gap-1 max-w-xs truncate">
                <MapPin class="h-3.5 w-3.5 shrink-0" />
                <span class="truncate">{{ sharedLocation }}</span>
              </span>
              <span v-if="sharedCategory" class="flex items-center gap-1 max-w-xs truncate">
                <Tag class="h-3.5 w-3.5 shrink-0" />
                <span class="truncate">{{ sharedCategory }}</span>
              </span>
            </div>
          </div>

          <!-- Desktop actions -->
          <div class="hidden sm:flex gap-2 shrink-0">
            <HintTooltip :label="t('print.printTask')">
              <Button
                data-testid="btn-print"
                variant="outline"
                size="icon"
                :aria-label="t('print.printTask')"
                @click="router.push({ name: 'print-task', params: { eventId: task!.id } })"
              >
                <Printer class="h-4 w-4" />
              </Button>
            </HintTooltip>
            <Button
              v-if="canManage && !hasBatches"
              data-testid="btn-edit-task"
              variant="outline"
              @click="router.push({ name: 'task-edit', params: { eventId: task.id } })"
            >
              <Pencil class="mr-2 h-4 w-4" />
              {{ t('duties.tasks.edit') }}
            </Button>
            <template v-if="canManage">
              <DropdownMenu>
                <DropdownMenuTrigger as-child>
                  <Button data-testid="btn-add-shifts">
                    <CalendarPlus class="mr-2 h-4 w-4" />
                    {{ t('duties.tasks.detail.addShifts') }}
                    <ChevronDown class="ml-1 h-3 w-3" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem
                    @click="router.push({ name: 'task-add-shifts', params: { eventId: task.id } })"
                  >
                    <CalendarPlus class="mr-2 h-4 w-4" />
                    {{ t('duties.tasks.detail.addShiftBatch') }}
                  </DropdownMenuItem>
                  <DropdownMenuItem @click="showCreateShiftDialog = true">
                    <Plus class="mr-2 h-4 w-4" />
                    {{ t('duties.tasks.detail.addSingleShift') }}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
              <HintTooltip :label="t('duties.tasks.delete')">
                <Button
                  data-testid="btn-delete-task"
                  variant="destructive"
                  size="icon"
                  :aria-label="t('duties.tasks.delete')"
                  @click="handleDeleteTask"
                >
                  <Trash2 class="h-4 w-4" />
                </Button>
              </HintTooltip>
            </template>
          </div>

          <!-- Mobile actions menu -->
          <div class="sm:hidden shrink-0">
            <DropdownMenu>
              <DropdownMenuTrigger as-child>
                <Button variant="outline" size="icon" :aria-label="t('common.actions.moreActions')">
                  <EllipsisVertical class="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  @click="router.push({ name: 'print-task', params: { eventId: task!.id } })"
                >
                  <Printer class="mr-2 h-4 w-4" />
                  {{ t('print.printTask') }}
                </DropdownMenuItem>
                <template v-if="canManage">
                  <DropdownMenuItem
                    v-if="!hasBatches"
                    @click="router.push({ name: 'task-edit', params: { eventId: task.id } })"
                  >
                    <Pencil class="mr-2 h-4 w-4" />
                    {{ t('duties.tasks.edit') }}
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    @click="router.push({ name: 'task-add-shifts', params: { eventId: task.id } })"
                  >
                    <CalendarPlus class="mr-2 h-4 w-4" />
                    {{ t('duties.tasks.detail.addShiftBatch') }}
                  </DropdownMenuItem>
                  <DropdownMenuItem @click="showCreateShiftDialog = true">
                    <Plus class="mr-2 h-4 w-4" />
                    {{ t('duties.tasks.detail.addSingleShift') }}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem class="text-destructive" @click="handleDeleteTask">
                    <Trash2 class="mr-2 h-4 w-4" />
                    {{ t('duties.tasks.delete') }}
                  </DropdownMenuItem>
                </template>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        <!-- Where it happens: mini map of the shared location -->
        <div
          v-if="sharedLocationDetail && (miniMapPin || canManage)"
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
            v-if="canManage"
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
      </div>

      <Separator />

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
              <h2 class="text-lg font-semibold">{{ t('duties.tasks.detail.myBookings') }}</h2>
              <Badge variant="default">
                {{
                  t('duties.tasks.detail.myBookingsCount', { count: myBookedShiftsForTask.length })
                }}
              </Badge>
            </div>
            <div class="flex flex-wrap gap-2">
              <Badge
                v-for="shift in myBookedShiftsForTask"
                :key="shift.id"
                variant="secondary"
                class="cursor-pointer px-3 py-1.5 text-sm hover:bg-secondary/80 hover:ring-1 hover:ring-primary/30 transition-colors"
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
              </Badge>
            </div>
            <Separator />
          </div>
        </div>
      </Transition>

      <!-- Duty Shifts -->
      <div data-testid="section-shifts" class="space-y-4">
        <h2 class="text-xl font-semibold">{{ t('duties.tasks.detail.shifts') }}</h2>

        <!-- Filters (only shown when multiple distinct values exist) -->
        <div v-if="hasFilters" class="flex flex-wrap gap-3">
          <!-- Location filter -->
          <div v-if="hasMultipleLocations" class="flex flex-wrap items-center gap-1.5">
            <MapPin class="h-4 w-4 text-muted-foreground" />
            <button
              class="rounded-full border px-3 py-1 text-sm transition-colors"
              :class="
                filterLocation === null
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'hover:bg-muted'
              "
              @click="filterLocation = null"
            >
              {{ t('duties.tasks.detail.allLocations') }}
            </button>
            <button
              v-for="loc in uniqueLocations"
              :key="loc"
              class="rounded-full border px-3 py-1 text-sm transition-colors"
              :class="
                filterLocation === loc
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'hover:bg-muted'
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
              class="rounded-full border px-3 py-1 text-sm transition-colors"
              :class="
                filterCategory === null
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'hover:bg-muted'
              "
              @click="filterCategory = null"
            >
              {{ t('duties.tasks.detail.allCategories') }}
            </button>
            <button
              v-for="cat in uniqueCategories"
              :key="cat"
              class="rounded-full border px-3 py-1 text-sm transition-colors"
              :class="
                filterCategory === cat
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'hover:bg-muted'
              "
              @click="filterCategory = cat"
            >
              {{ cat }}
            </button>
          </div>
        </div>

        <!-- Hint for users with no bookings; a locked task says how to get in -->
        <p
          v-if="teamPickHint && shifts.length > 0"
          class="text-sm text-muted-foreground"
          data-testid="task-team-pick-hint"
        >
          {{ teamPickHint }}
        </p>
        <p
          v-else-if="myBookedShiftsForTask.length === 0 && shifts.length > 0"
          class="text-sm text-muted-foreground"
        >
          {{ t('duties.tasks.detail.noBookingsYet') }}
        </p>

        <div v-if="shifts.length === 0" class="text-center py-8 text-muted-foreground">
          {{ t('duties.shifts.empty') }}
        </div>

        <!-- Batch-grouped shifts -->
        <div v-else class="space-y-6">
          <template
            v-for="(event, eventIdx) in visibleBatchGroups"
            :key="event.batch?.id ?? 'unbatched'"
          >
            <div class="space-y-3">
              <!-- Batch header (only when there are multiple batches) -->
              <div v-if="hasBatches" class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <h3 class="font-semibold text-lg">
                    {{
                      event.batch
                        ? batchLabel(event.batch)
                        : t('duties.tasks.detail.unbatchedShifts')
                    }}
                  </h3>
                  <Badge variant="outline">
                    {{
                      t('duties.tasks.detail.shiftsCount', {
                        count: filterShifts(event.shifts).length,
                      })
                    }}
                  </Badge>
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
                <div v-if="canManage && event.batch" class="flex gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    @click="
                      router.push({
                        name: 'task-edit',
                        params: { eventId: task!.id },
                        query: { batchId: event.batch!.id },
                      })
                    "
                  >
                    <Pencil class="mr-1.5 h-3.5 w-3.5" />
                    {{ t('duties.tasks.edit') }}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    class="text-destructive hover:text-destructive"
                    :aria-label="t('duties.tasks.detail.deleteBatch')"
                    @click="handleDeleteBatch(event.batch!)"
                  >
                    <Trash2 class="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>

              <!-- Shifts grouped by date within this batch -->
              <div
                v-for="[date, shifts] in groupByDate(filterShifts(event.shifts))"
                :key="date"
                class="space-y-2"
              >
                <div class="flex items-center gap-2">
                  <h3 class="font-medium">{{ formatDateLabel(date) }}</h3>
                  <Badge variant="outline">
                    {{ t('duties.tasks.detail.shiftsCount', { count: shifts.length }) }}
                  </Badge>
                </div>
                <div class="grid grid-cols-3 gap-1.5 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6">
                  <Card
                    v-for="shift in shifts"
                    :key="shift.id"
                    :data-testid="'shift-card-' + shift.id"
                    class="event relative cursor-pointer select-none transition-all"
                    :class="[
                      myBookedShiftIds.has(shift.id)
                        ? 'ring-2 ring-primary bg-primary/5'
                        : isShiftFull(shift)
                          ? 'opacity-40 cursor-not-allowed'
                          : shift.locked_by_team
                            ? 'border-dashed bg-muted/30 text-muted-foreground shadow-none hover:ring-1 hover:ring-border'
                            : shift.collides_with_my_booking
                              ? 'opacity-50 cursor-not-allowed border-dashed border-destructive/50'
                              : 'hover:ring-1 hover:ring-primary/40',
                      busyShiftId === shift.id ? 'opacity-60 pointer-events-none' : '',
                    ]"
                    :title="
                      shift.locked_by_team && !myBookedShiftIds.has(shift.id)
                        ? t('teamLocks.gate.lockedShift', { name: shift.team_name })
                        : shift.collides_with_my_booking
                          ? t('duties.shifts.detail.clashesWithMine')
                          : undefined
                    "
                    @click="handleShiftClick(shift)"
                  >
                    <CardContent class="px-3 py-2">
                      <!-- Booked checkmark -->
                      <div v-if="myBookedShiftIds.has(shift.id)" class="absolute top-1.5 right-1.5">
                        <Check class="h-4 w-4 text-primary" />
                      </div>
                      <!-- Overlaps a shift the user already holds -->
                      <div
                        v-else-if="shift.collides_with_my_booking"
                        class="absolute top-1.5 right-1.5"
                        :data-testid="'shift-clash-' + shift.id"
                      >
                        <CalendarX2
                          class="h-4 w-4 text-destructive"
                          :aria-label="t('duties.shifts.detail.clashesWithMine')"
                        />
                      </div>
                      <!-- Reserved for a team the user is not in -->
                      <div
                        v-else-if="shift.locked_by_team"
                        class="absolute top-1.5 right-1.5"
                        :data-testid="'shift-team-locked-' + shift.id"
                      >
                        <Lock
                          class="h-3.5 w-3.5 text-muted-foreground"
                          role="img"
                          :aria-label="t('teamLocks.gate.lockedShift', { name: shift.team_name })"
                        />
                      </div>

                      <!-- Expand button (visible on hover) -->
                      <HintTooltip :label="t('duties.shifts.detail.openDetails')">
                        <button
                          class="absolute top-1 left-1 flex h-5 w-5 items-center justify-center rounded-sm opacity-0 transition-opacity event-hover:opacity-100 hover:bg-muted"
                          :aria-label="t('duties.shifts.detail.openDetails')"
                          @click.stop="openShiftDetail(shift)"
                        >
                          <Expand class="h-3 w-3 text-muted-foreground" />
                        </button>
                      </HintTooltip>

                      <!-- Time -->
                      <p class="text-center text-lg font-mono font-semibold">
                        <template v-if="shift.start_time || shift.end_time">
                          {{ formatTime(shift.start_time)
                          }}{{ shift.start_time && shift.end_time ? ' - ' : ''
                          }}{{ formatTime(shift.end_time) }}
                        </template>
                        <template v-else>
                          {{ shift.title }}
                        </template>
                      </p>

                      <!-- Category / Location badges (only when not in batch header and multiple values exist) -->
                      <div
                        v-if="
                          !hasBatches &&
                          ((hasMultipleLocations && shift.location) ||
                            (hasMultipleCategories && shift.category))
                        "
                        class="mt-1 flex flex-wrap justify-center gap-1"
                      >
                        <Badge
                          v-if="hasMultipleCategories && shift.category"
                          variant="outline"
                          class="text-sm px-2 py-0"
                        >
                          {{ shift.category }}
                        </Badge>
                        <Badge
                          v-if="hasMultipleLocations && shift.location"
                          variant="secondary"
                          class="text-sm px-2 py-0"
                        >
                          {{ shift.location }}
                        </Badge>
                      </div>

                      <!-- Availability -->
                      <p
                        class="mt-1 text-center text-sm text-muted-foreground"
                        :class="isShiftFull(shift) ? 'text-destructive' : ''"
                      >
                        {{ shift.current_bookings ?? 0 }}/{{ shift.max_bookings ?? 1 }}
                      </p>

                      <!-- Admin delete (stop propagation so it doesn't trigger booking) -->
                      <HintTooltip v-if="canManage" :label="t('duties.shifts.delete')">
                        <Button
                          variant="ghost"
                          size="icon"
                          class="absolute bottom-0.5 right-0.5 h-5 w-5"
                          :aria-label="t('duties.shifts.delete')"
                          @click.stop="handleDeleteShift(shift)"
                        >
                          <Trash2 class="h-3 w-3 text-destructive" />
                        </Button>
                      </HintTooltip>
                    </CardContent>
                  </Card>
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
      </div>
    </template>

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
      <ResponsiveDialogContent>
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
              <Input v-model="slotForm.title" required />
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
            <Button type="submit">{{ t('common.actions.create') }}</Button>
          </ResponsiveDialogFooter>
        </form>
      </ResponsiveDialogContent>
    </ResponsiveDialog>

    <LocationFormDialog
      v-if="sharedLocationDetail && task?.event_id"
      v-model:open="locationFormOpen"
      :event-id="task.event_id"
      :location="sharedLocationDetail"
      @saved="onLocationSaved"
    />

    <!-- Shift Detail Dialog -->
    <ShiftDetailDialog
      v-model:open="showShiftDetail"
      :shift="selectedShift"
      :task-name="task?.name"
      :show-task-link="false"
      :my-booking="selectedShift ? (getBookingForShift(selectedShift.id) ?? null) : null"
      @booking-updated="reloadShiftsAndBookings"
      @team-joined="onTeamJoined"
    />
  </div>
</template>
