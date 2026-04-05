<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import type { DateValue } from '@internationalized/date'
import {
  ArrowLeft,
  CalendarCheck,
  CalendarPlus,
  Check,
  ChevronDown,
  EllipsisVertical,
  Expand,
  Info,
  MapPin,
  Pencil,
  Plus,
  Printer,
  Tag,
  Trash2,
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import Input from '@/components/ui/input/Input.vue'
import Label from '@/components/ui/label/Label.vue'
import Separator from '@/components/ui/separator/Separator.vue'

import DeleteConfirmationDialog from '@/components/events/DeleteConfirmationDialog.vue'
import SlotDetailDialog from '@/components/events/SlotDetailDialog.vue'
import StatusDropdown from '@/components/events/StatusDropdown.vue'

import type {
  BookingRead,
  DutySlotListResponse,
  DutySlotRead,
  EventRead,
  MyBookingsListResponse,
  SlotBatchRead,
} from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { formatDate } from '@/lib/format'

const { t } = useI18n()
const { formatTime, formatDateLabel } = useFormatters()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const breadcrumbStore = useBreadcrumbStore()
const { get, post, patch, delete: del } = useAuthenticatedClient()
const { confirm, confirmDestructive } = useDialog()

const eventId = computed(() => route.params.eventId as string)
const event = ref<EventRead | null>(null)
const dutySlots = ref<DutySlotRead[]>([])
const myBookings = ref<BookingRead[]>([])
const batches = ref<SlotBatchRead[]>([])
const loading = ref(false)
const showCreateSlotDialog = ref(false)

// Create slot form
const slotForm = ref({
  title: '',
  description: '',
  start_time: '',
  end_time: '',
  location: '',
  category: '',
  max_bookings: 5,
})
const slotDate = ref<DateValue>()

// --- Batch grouping ---
const hasBatches = computed(() => batches.value.length > 1)

interface BatchGroup {
  batch: SlotBatchRead | null
  slots: DutySlotRead[]
}

const slotsByBatch = computed<BatchGroup[]>(() => {
  if (!hasBatches.value) {
    // No batches — return all slots as a single group
    return [{ batch: null, slots: dutySlots.value }]
  }

  const batchMap = new Map<string, DutySlotRead[]>()
  const unbatched: DutySlotRead[] = []

  for (const slot of dutySlots.value) {
    if (slot.batch_id) {
      if (!batchMap.has(slot.batch_id)) batchMap.set(slot.batch_id, [])
      batchMap.get(slot.batch_id)!.push(slot)
    } else {
      unbatched.push(slot)
    }
  }

  const groups: BatchGroup[] = []

  // Add batch groups in order
  for (const batch of batches.value) {
    const slots = batchMap.get(batch.id) ?? []
    if (slots.length > 0) {
      groups.push({ batch, slots })
    }
  }

  // Add unbatched slots if any
  if (unbatched.length > 0) {
    groups.push({ batch: null, slots: unbatched })
  }

  return groups
})

// --- Filters ---
const filterLocation = ref<string | null>(null)
const filterCategory = ref<string | null>(null)

// --- Unique values for filters (only shown when > 1 distinct value) ---
const uniqueLocations = computed(() => {
  const vals = new Set<string>()
  for (const slot of dutySlots.value) {
    if (slot.location) vals.add(slot.location)
  }
  return [...vals].sort()
})

const uniqueCategories = computed(() => {
  const vals = new Set<string>()
  for (const slot of dutySlots.value) {
    if (slot.category) vals.add(slot.category)
  }
  return [...vals].sort()
})

const hasMultipleLocations = computed(() => uniqueLocations.value.length > 1)
const hasMultipleCategories = computed(() => uniqueCategories.value.length > 1)
const hasFilters = computed(() => hasMultipleLocations.value || hasMultipleCategories.value)
const isFilterActive = computed(
  () => filterLocation.value !== null || filterCategory.value !== null,
)

// Visible batch groups (groups with at least one slot matching the filter)
const visibleBatchGroups = computed(() => {
  return slotsByBatch.value.filter((group) => filterSlots(group.slots).length > 0)
})

// Count of slots hidden by the active filter
const hiddenSlotsCount = computed(() => {
  if (!isFilterActive.value) return 0
  return (
    dutySlots.value.length -
    dutySlots.value.filter((slot) => {
      if (filterLocation.value && slot.location !== filterLocation.value) return false
      if (filterCategory.value && slot.category !== filterCategory.value) return false
      return true
    }).length
  )
})

// Shared properties (same across all slots — shown once in header)
const sharedLocation = computed(() => {
  if (uniqueLocations.value.length === 1) return uniqueLocations.value[0]
  return null
})
const sharedCategory = computed(() => {
  if (uniqueCategories.value.length === 1) return uniqueCategories.value[0]
  return null
})

// Filter slots within a group
const filterSlots = (slots: DutySlotRead[]) => {
  return slots.filter((slot) => {
    if (filterLocation.value && slot.location !== filterLocation.value) return false
    if (filterCategory.value && slot.category !== filterCategory.value) return false
    return true
  })
}

// Group slots by date (for rendering within a batch group)
const groupByDate = (slots: DutySlotRead[]) => {
  const groups: Record<string, DutySlotRead[]> = {}
  for (const slot of slots) {
    const date = slot.date
    if (!groups[date]) groups[date] = []
    groups[date].push(slot)
  }
  for (const dateSlots of Object.values(groups)) {
    dateSlots.sort(
      (a, b) =>
        (a.start_time ?? '').localeCompare(b.start_time ?? '') ||
        (a.end_time ?? '').localeCompare(b.end_time ?? ''),
    )
  }
  return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b))
}

const myBookedSlotIds = computed(() => {
  return new Set(
    myBookings.value.filter((b) => b.status === 'confirmed').map((b) => b.duty_slot_id),
  )
})

const getBookingForSlot = (slotId: string) => {
  return myBookings.value.find((b) => b.duty_slot_id === slotId && b.status === 'confirmed')
}

const isSlotFull = (slot: DutySlotRead) => {
  return (slot.current_bookings ?? 0) >= (slot.max_bookings ?? 1)
}

// My booked slots with full slot details (for summary)
const myBookedSlotsForEvent = computed(() => {
  return dutySlots.value
    .filter((s) => myBookedSlotIds.value.has(s.id))
    .sort(
      (a, b) =>
        a.date.localeCompare(b.date) || (a.start_time ?? '').localeCompare(b.start_time ?? ''),
    )
})

const busySlotId = ref<string | null>(null)

// Slot detail dialog
const showSlotDetail = ref(false)
const selectedSlot = ref<DutySlotRead | null>(null)

const openSlotDetail = (slot: DutySlotRead) => {
  selectedSlot.value = slot
  showSlotDetail.value = true
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

const countConfirmedBookings = (slots: DutySlotRead[]) => {
  return slots.reduce((sum, s) => sum + (s.current_bookings ?? 0), 0)
}

const handleSlotClick = async (slot: DutySlotRead) => {
  if (busySlotId.value) return
  busySlotId.value = slot.id

  try {
    if (myBookedSlotIds.value.has(slot.id)) {
      const booking = getBookingForSlot(slot.id)
      if (!booking) return
      const confirmed = await confirmDestructive(t('duties.bookings.cancelConfirm'))
      if (!confirmed) return
      await del({ url: `/bookings/${booking.id}` })
      toast.success(t('duties.bookings.cancelSuccess'))
    } else {
      if (isSlotFull(slot)) return
      const confirmed = await confirm(t('duties.bookings.bookConfirm'))
      if (!confirmed) return
      await post({ url: '/bookings/', body: { duty_slot_id: slot.id } })
      toast.success(t('duties.bookings.bookSuccess'))
    }
    await Promise.all([loadDutySlots(), loadMyBookings()])
  } catch (error) {
    toastApiError(error)
  } finally {
    busySlotId.value = null
  }
}

const batchLabel = (batch: SlotBatchRead) => {
  return batch.label || `${formatDate(batch.start_date)} – ${formatDate(batch.end_date)}`
}

const loadEvent = async () => {
  loading.value = true
  try {
    const response = await get<{ data: EventRead }>({
      url: `/events/${eventId.value}`,
    })
    event.value = response.data

    // Set dynamic breadcrumbs
    breadcrumbStore.setBreadcrumbs([
      {
        title: 'Events',
        titleKey: 'duties.events.title',
        to: { name: 'events' },
      },
      {
        title: response.data.name,
      },
    ])
  } catch (error) {
    toastApiError(error)
    router.push({ name: 'events' })
  } finally {
    loading.value = false
  }
}

const loadDutySlots = async () => {
  try {
    const response = await get<{ data: DutySlotListResponse }>({
      url: '/duty-slots/',
      query: { event_id: eventId.value, limit: 200 },
    })
    dutySlots.value = response.data.items
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
    const response = await get<{ data: SlotBatchRead[] }>({
      url: `/events/${eventId.value}/batches`,
    })
    batches.value = response.data
  } catch {
    // Non-critical — older events may not have batches
  }
}

const handleStatusChange = async (status: 'draft' | 'published' | 'archived') => {
  if (!event.value || event.value.status === status) return
  try {
    const response = await patch<{ data: EventRead }>({
      url: `/events/${event.value.id}`,
      body: { status },
    })
    event.value = response.data
    toast.success(t(`duties.events.statuses.${status}`))
  } catch (error) {
    toastApiError(error)
  }
}

const handleDeleteEvent = () => {
  const bookingCount = countConfirmedBookings(dutySlots.value)
  openDeleteDialog(t('duties.events.deleteConfirm'), bookingCount, async () => {
    try {
      const query: Record<string, string> = {}
      if (deleteReason.value.trim()) query.cancellation_reason = deleteReason.value.trim()
      await del({ url: `/events/${eventId.value}`, query })
      toast.success(t('duties.events.delete'))
      router.push({ name: 'events' })
    } catch (error) {
      toastApiError(error)
    }
  })
}

const handleDeleteBatch = (batch: SlotBatchRead) => {
  const batchSlots = dutySlots.value.filter((s) => s.batch_id === batch.id)
  const bookingCount = countConfirmedBookings(batchSlots)
  openDeleteDialog(t('duties.events.detail.deleteBatchConfirm'), bookingCount, async () => {
    try {
      const query: Record<string, string> = {}
      if (deleteReason.value.trim()) query.cancellation_reason = deleteReason.value.trim()
      await del({ url: `/events/${eventId.value}/batches/${batch.id}`, query })
      toast.success(t('duties.events.detail.deleteBatchSuccess'))
      await Promise.all([loadDutySlots(), loadBatches()])
    } catch (error) {
      toastApiError(error)
    }
  })
}

const handleCreateSlot = async () => {
  if (!slotDate.value) return
  try {
    await post({
      url: '/duty-slots/',
      body: {
        event_id: eventId.value,
        title: slotForm.value.title,
        description: slotForm.value.description || undefined,
        date: slotDate.value.toString(),
        start_time: slotForm.value.start_time || undefined,
        end_time: slotForm.value.end_time || undefined,
        location: slotForm.value.location || undefined,
        category: slotForm.value.category || undefined,
        max_bookings: slotForm.value.max_bookings,
      },
    })
    showCreateSlotDialog.value = false
    slotForm.value = {
      title: '',
      description: '',
      start_time: '',
      end_time: '',
      location: '',
      category: '',
      max_bookings: 5,
    }
    slotDate.value = undefined
    toast.success(t('duties.dutySlots.create'))
    await loadDutySlots()
  } catch (error) {
    toastApiError(error)
  }
}

const handleDeleteSlot = (slot: DutySlotRead) => {
  const bookingCount = slot.current_bookings ?? 0
  openDeleteDialog(t('duties.dutySlots.deleteConfirm'), bookingCount, async () => {
    try {
      const query: Record<string, string> = {}
      if (deleteReason.value.trim()) query.cancellation_reason = deleteReason.value.trim()
      await del({ url: `/duty-slots/${slot.id}`, query })
      toast.success(t('duties.dutySlots.delete'))
      await loadDutySlots()
    } catch (error) {
      toastApiError(error)
    }
  })
}

const reloadSlotsAndBookings = () => Promise.all([loadDutySlots(), loadMyBookings()])

onMounted(async () => {
  await loadEvent()
  await Promise.all([loadDutySlots(), loadMyBookings(), loadBatches()])
})
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <!-- Loading -->
    <div v-if="loading" class="text-center py-12 text-muted-foreground">
      {{ t('common.states.loading') }}
    </div>

    <template v-else-if="event">
      <!-- Back button + Header -->
      <div class="space-y-4">
        <Button data-testid="btn-back" variant="ghost" size="sm" @click="router.push({ name: 'events' })">
          <ArrowLeft class="mr-2 h-4 w-4" />
          {{ t('common.actions.back') }}
        </Button>

        <!-- Draft banner -->
        <Alert
          v-if="event.status === 'draft'"
          variant="default"
          class="border-amber-500/50 bg-amber-50 text-amber-900 dark:bg-amber-950/30 dark:text-amber-200 dark:border-amber-500/30"
        >
          <Info class="h-4 w-4 text-amber-600 dark:text-amber-400" />
          <AlertDescription>
            {{ t('duties.events.draftBanner') }}
          </AlertDescription>
        </Alert>

        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0 flex-1 space-y-2">
            <div class="flex items-center gap-3 flex-wrap">
              <h1 data-testid="page-heading" class="text-3xl font-bold line-clamp-2 break-words">{{ event.name }}</h1>
              <StatusDropdown
                data-testid="event-status"
                :status="event.status"
                i18n-prefix="duties.events.statuses"
                :editable="authStore.isAdmin"
                @change="handleStatusChange"
              />
            </div>
            <p v-if="event.description" class="text-muted-foreground line-clamp-3 break-words">
              {{ event.description }}
            </p>
            <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
              <span>{{ formatDate(event.start_date) }} - {{ formatDate(event.end_date) }}</span>
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
            <Button
              data-testid="btn-print"
              variant="outline"
              size="icon"
              :title="t('print.printEvent')"
              @click="router.push({ name: 'print-event', params: { eventId: event!.id } })"
            >
              <Printer class="h-4 w-4" />
            </Button>
            <Button
              v-if="authStore.isAdmin && !hasBatches"
              data-testid="btn-edit-event"
              variant="outline"
              @click="router.push({ name: 'event-edit', params: { eventId: event.id } })"
            >
              <Pencil class="mr-2 h-4 w-4" />
              {{ t('duties.events.edit') }}
            </Button>
            <template v-if="authStore.isAdmin">
              <DropdownMenu>
                <DropdownMenuTrigger as-child>
                  <Button data-testid="btn-add-slots">
                    <CalendarPlus class="mr-2 h-4 w-4" />
                    {{ t('duties.events.detail.addSlots') }}
                    <ChevronDown class="ml-1 h-3 w-3" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem
                    @click="router.push({ name: 'event-add-slots', params: { eventId: event.id } })"
                  >
                    <CalendarPlus class="mr-2 h-4 w-4" />
                    {{ t('duties.events.detail.addSlotBatch') }}
                  </DropdownMenuItem>
                  <DropdownMenuItem @click="showCreateSlotDialog = true">
                    <Plus class="mr-2 h-4 w-4" />
                    {{ t('duties.events.detail.addSingleSlot') }}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
              <Button data-testid="btn-delete-event" variant="destructive" size="icon" @click="handleDeleteEvent">
                <Trash2 class="h-4 w-4" />
              </Button>
            </template>
          </div>

          <!-- Mobile actions menu -->
          <div class="sm:hidden shrink-0">
            <DropdownMenu>
              <DropdownMenuTrigger as-child>
                <Button variant="outline" size="icon">
                  <EllipsisVertical class="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  @click="router.push({ name: 'print-event', params: { eventId: event!.id } })"
                >
                  <Printer class="mr-2 h-4 w-4" />
                  {{ t('print.printEvent') }}
                </DropdownMenuItem>
                <template v-if="authStore.isAdmin">
                  <DropdownMenuItem
                    v-if="!hasBatches"
                    @click="router.push({ name: 'event-edit', params: { eventId: event.id } })"
                  >
                    <Pencil class="mr-2 h-4 w-4" />
                    {{ t('duties.events.edit') }}
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    @click="router.push({ name: 'event-add-slots', params: { eventId: event.id } })"
                  >
                    <CalendarPlus class="mr-2 h-4 w-4" />
                    {{ t('duties.events.detail.addSlotBatch') }}
                  </DropdownMenuItem>
                  <DropdownMenuItem @click="showCreateSlotDialog = true">
                    <Plus class="mr-2 h-4 w-4" />
                    {{ t('duties.events.detail.addSingleSlot') }}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem class="text-destructive" @click="handleDeleteEvent">
                    <Trash2 class="mr-2 h-4 w-4" />
                    {{ t('duties.events.delete') }}
                  </DropdownMenuItem>
                </template>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
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
        <div v-if="myBookedSlotsForEvent.length > 0">
          <div class="overflow-hidden space-y-3">
            <div class="flex items-center gap-2">
              <CalendarCheck class="h-5 w-5 text-primary" />
              <h2 class="text-lg font-semibold">{{ t('duties.events.detail.myBookings') }}</h2>
              <Badge variant="default">
                {{
                  t('duties.events.detail.myBookingsCount', { count: myBookedSlotsForEvent.length })
                }}
              </Badge>
            </div>
            <div class="flex flex-wrap gap-2">
              <Badge
                v-for="slot in myBookedSlotsForEvent"
                :key="slot.id"
                variant="secondary"
                class="cursor-pointer px-3 py-1.5 text-sm hover:bg-secondary/80 hover:ring-1 hover:ring-primary/30 transition-colors"
                @click="openSlotDetail(slot)"
              >
                {{ formatDateLabel(slot.date) }}
                <template v-if="slot.start_time">
                  &middot; {{ formatTime(slot.start_time)
                  }}<template v-if="slot.end_time"> - {{ formatTime(slot.end_time) }}</template>
                </template>
                <template v-if="hasMultipleLocations && slot.location">
                  &middot; {{ slot.location }}</template
                >
                <template v-if="hasMultipleCategories && slot.category">
                  &middot; {{ slot.category }}</template
                >
              </Badge>
            </div>
            <Separator />
          </div>
        </div>
      </Transition>

      <!-- Duty Slots -->
      <div data-testid="section-duty-slots" class="space-y-4">
        <h2 class="text-xl font-semibold">{{ t('duties.events.detail.slots') }}</h2>

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
              {{ t('duties.events.detail.allLocations') }}
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
              {{ t('duties.events.detail.allCategories') }}
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

        <!-- Hint for users with no bookings -->
        <p
          v-if="myBookedSlotsForEvent.length === 0 && dutySlots.length > 0"
          class="text-sm text-muted-foreground"
        >
          {{ t('duties.events.detail.noBookingsYet') }}
        </p>

        <div v-if="dutySlots.length === 0" class="text-center py-8 text-muted-foreground">
          {{ t('duties.dutySlots.empty') }}
        </div>

        <!-- Batch-grouped slots -->
        <div v-else class="space-y-6">
          <template
            v-for="(group, groupIdx) in visibleBatchGroups"
            :key="group.batch?.id ?? 'unbatched'"
          >
            <div class="space-y-3">
              <!-- Batch header (only when there are multiple batches) -->
              <div v-if="hasBatches" class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <h3 class="font-semibold text-lg">
                    {{
                      group.batch
                        ? batchLabel(group.batch)
                        : t('duties.events.detail.unbatchedSlots')
                    }}
                  </h3>
                  <Badge variant="outline">
                    {{
                      t('duties.events.detail.slotsCount', {
                        count: filterSlots(group.slots).length,
                      })
                    }}
                  </Badge>
                  <template v-if="group.batch">
                    <Badge v-if="group.batch.location" variant="secondary" class="text-xs">
                      <MapPin class="mr-1 h-3 w-3" />
                      {{ group.batch.location }}
                    </Badge>
                    <Badge v-if="group.batch.category" variant="outline" class="text-xs">
                      <Tag class="mr-1 h-3 w-3" />
                      {{ group.batch.category }}
                    </Badge>
                  </template>
                </div>
                <div v-if="authStore.isAdmin && group.batch" class="flex gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    @click="
                      router.push({
                        name: 'event-edit',
                        params: { eventId: event!.id },
                        query: { batchId: group.batch!.id },
                      })
                    "
                  >
                    <Pencil class="mr-1.5 h-3.5 w-3.5" />
                    {{ t('duties.events.edit') }}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    class="text-destructive hover:text-destructive"
                    @click="handleDeleteBatch(group.batch!)"
                  >
                    <Trash2 class="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>

              <!-- Slots grouped by date within this batch -->
              <div
                v-for="[date, slots] in groupByDate(filterSlots(group.slots))"
                :key="date"
                class="space-y-2"
              >
                <div class="flex items-center gap-2">
                  <h3 class="font-medium">{{ formatDateLabel(date) }}</h3>
                  <Badge variant="outline">
                    {{ t('duties.events.detail.slotsCount', { count: slots.length }) }}
                  </Badge>
                </div>
                <div class="grid grid-cols-3 gap-1.5 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6">
                  <Card
                    v-for="slot in slots"
                    :key="slot.id"
                    class="group relative cursor-pointer select-none transition-all"
                    :class="[
                      myBookedSlotIds.has(slot.id)
                        ? 'ring-2 ring-primary bg-primary/5'
                        : isSlotFull(slot)
                          ? 'opacity-40 cursor-not-allowed'
                          : 'hover:ring-1 hover:ring-primary/40',
                      busySlotId === slot.id ? 'opacity-60 pointer-events-none' : '',
                    ]"
                    @click="handleSlotClick(slot)"
                  >
                    <CardContent class="px-3 py-2">
                      <!-- Booked checkmark -->
                      <div v-if="myBookedSlotIds.has(slot.id)" class="absolute top-1.5 right-1.5">
                        <Check class="h-4 w-4 text-primary" />
                      </div>

                      <!-- Expand button (visible on hover) -->
                      <button
                        class="absolute top-1 left-1 flex h-5 w-5 items-center justify-center rounded-sm opacity-0 transition-opacity group-hover:opacity-100 hover:bg-muted"
                        :title="t('duties.dutySlots.detail.openDetails')"
                        @click.stop="openSlotDetail(slot)"
                      >
                        <Expand class="h-3 w-3 text-muted-foreground" />
                      </button>

                      <!-- Time -->
                      <p class="text-center text-lg font-mono font-semibold">
                        <template v-if="slot.start_time || slot.end_time">
                          {{ formatTime(slot.start_time)
                          }}{{ slot.start_time && slot.end_time ? ' - ' : ''
                          }}{{ formatTime(slot.end_time) }}
                        </template>
                        <template v-else>
                          {{ slot.title }}
                        </template>
                      </p>

                      <!-- Category / Location badges (only when not in batch header and multiple values exist) -->
                      <div
                        v-if="
                          !hasBatches &&
                          ((hasMultipleLocations && slot.location) ||
                            (hasMultipleCategories && slot.category))
                        "
                        class="mt-1 flex flex-wrap justify-center gap-1"
                      >
                        <Badge
                          v-if="hasMultipleCategories && slot.category"
                          variant="outline"
                          class="text-sm px-2 py-0"
                        >
                          {{ slot.category }}
                        </Badge>
                        <Badge
                          v-if="hasMultipleLocations && slot.location"
                          variant="secondary"
                          class="text-sm px-2 py-0"
                        >
                          {{ slot.location }}
                        </Badge>
                      </div>

                      <!-- Availability -->
                      <p
                        class="mt-1 text-center text-sm text-muted-foreground"
                        :class="isSlotFull(slot) ? 'text-destructive' : ''"
                      >
                        {{ slot.current_bookings ?? 0 }}/{{ slot.max_bookings ?? 1 }}
                      </p>

                      <!-- Admin delete (stop propagation so it doesn't trigger booking) -->
                      <Button
                        v-if="authStore.isAdmin"
                        variant="ghost"
                        size="icon"
                        class="absolute bottom-0.5 right-0.5 h-5 w-5"
                        @click.stop="handleDeleteSlot(slot)"
                      >
                        <Trash2 class="h-3 w-3 text-destructive" />
                      </Button>
                    </CardContent>
                  </Card>
                </div>
              </div>

              <!-- Separator between batch groups -->
              <Separator v-if="hasBatches && groupIdx < visibleBatchGroups.length - 1" />
            </div>
          </template>

          <!-- Hidden slots info -->
          <p v-if="hiddenSlotsCount > 0" class="text-sm text-muted-foreground text-center py-2">
            {{ t('duties.events.detail.hiddenSlots', { count: hiddenSlotsCount }) }}
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

    <!-- Create Slot Dialog -->
    <Dialog v-model:open="showCreateSlotDialog">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ t('duties.dutySlots.create') }}</DialogTitle>
          <DialogDescription>{{ t('duties.events.detail.addSlot') }}</DialogDescription>
        </DialogHeader>
        <form class="space-y-4" @submit.prevent="handleCreateSlot">
          <div class="space-y-2">
            <Label>{{ t('duties.dutySlots.fields.title') }}</Label>
            <Input v-model="slotForm.title" required />
          </div>
          <div class="space-y-2">
            <Label>{{ t('duties.dutySlots.fields.description') }}</Label>
            <Input v-model="slotForm.description" />
          </div>
          <div class="space-y-2">
            <Label>{{ t('duties.dutySlots.fields.date') }}</Label>
            <DatePicker v-model="slotDate" :placeholder="t('duties.dutySlots.pickDate')" />
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <Label>{{ t('duties.dutySlots.fields.startTime') }}</Label>
              <Input v-model="slotForm.start_time" type="time" />
            </div>
            <div class="space-y-2">
              <Label>{{ t('duties.dutySlots.fields.endTime') }}</Label>
              <Input v-model="slotForm.end_time" type="time" />
            </div>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <Label>{{ t('duties.dutySlots.fields.location') }}</Label>
              <Input v-model="slotForm.location" />
            </div>
            <div class="space-y-2">
              <Label>{{ t('duties.dutySlots.fields.category') }}</Label>
              <Input v-model="slotForm.category" />
            </div>
          </div>
          <div class="space-y-2">
            <Label>{{ t('duties.dutySlots.fields.maxBookings') }}</Label>
            <Input v-model.number="slotForm.max_bookings" type="number" min="1" required />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" @click="showCreateSlotDialog = false">
              {{ t('common.actions.cancel') }}
            </Button>
            <Button type="submit">{{ t('common.actions.create') }}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>

    <!-- Slot Detail Dialog -->
    <SlotDetailDialog
      v-model:open="showSlotDetail"
      :duty-slot="selectedSlot"
      :event-name="event?.name"
      :show-event-link="false"
      :my-booking="selectedSlot ? (getBookingForSlot(selectedSlot.id) ?? null) : null"
      @booking-updated="reloadSlotsAndBookings"
    />
  </div>
</template>
