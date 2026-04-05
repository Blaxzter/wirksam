<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import {
  AlertCircle,
  Calendar,
  CalendarDays,
  Clock,
  Layers,
  MapPin,
  Search,
  Trash2,
  XCircle,
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useRouter } from 'vue-router'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'
import { useFormatters } from '@/composables/useFormatters'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { DateRangePicker } from '@/components/ui/date-range-picker'
import Input from '@/components/ui/input/Input.vue'
import Separator from '@/components/ui/separator/Separator.vue'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

import type { BookingReadWithSlot, MyBookingsListResponse } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const { t, locale } = useI18n()
const { formatTime, formatDateLabel } = useFormatters()
const { get, delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()
const router = useRouter()

const bookings = ref<BookingReadWithSlot[]>([])
const loading = ref(false)

const openBookingDetail = (booking: BookingReadWithSlot) => {
  router.push({ name: 'booking-detail', params: { bookingId: booking.id } })
}

// --- Filter state ---
const dateFrom = ref<string | null>(null)
const dateTo = ref<string | null>(null)
const showCancelled = ref(false)

// Marked days for the date range picker
const markedDays = ref<Set<string>>(new Set())

async function handleVisibleMonth(range: { from: string; to: string }) {
  try {
    const res = await get<{ data: string[] }>({
      url: '/bookings/me/active-dates',
      query: { date_from: range.from, date_to: range.to },
    })
    markedDays.value = new Set(res.data)
  } catch {
    // Non-critical
  }
}

// --- Grouping state (persisted in localStorage) ---
type GroupMode = 'none' | 'date' | 'event' | 'location'
const STORAGE_KEY = 'wirksam:bookings:groupBy'
const activeGrouping = ref<GroupMode>((localStorage.getItem(STORAGE_KEY) as GroupMode) || 'none')

watch(activeGrouping, (v) => localStorage.setItem(STORAGE_KEY, v))

const toggleGrouping = (mode: GroupMode) => {
  activeGrouping.value = activeGrouping.value === mode ? 'none' : mode
}

const groupingOptions = computed(() => [
  { mode: 'date' as const, icon: CalendarDays, label: t('duties.bookings.groupBy.date') },
  { mode: 'event' as const, icon: Layers, label: t('duties.bookings.groupBy.event') },
  { mode: 'location' as const, icon: MapPin, label: t('duties.bookings.groupBy.location') },
])

// --- Grouping logic ---
interface BookingGroup {
  key: string
  label: string
  bookings: BookingReadWithSlot[]
}

const searchQuery = ref('')

const filteredBookings = computed(() => {
  let result = bookings.value
  if (!showCancelled.value) {
    result = result.filter((b) => b.status !== 'cancelled')
  }
  const query = searchQuery.value.trim().toLowerCase()
  if (query) {
    result = result.filter((b) => {
      const slot = b.duty_slot
      if (!slot) return false
      return (
        slot.title?.toLowerCase().includes(query) ||
        slot.event_name?.toLowerCase().includes(query) ||
        slot.location?.toLowerCase().includes(query)
      )
    })
  }
  return result
})

const sortedBookings = computed(() =>
  [...filteredBookings.value].sort((a, b) => {
    const dateA = slotDate(a) ?? ''
    const dateB = slotDate(b) ?? ''
    if (dateA !== dateB) return dateA.localeCompare(dateB)
    const timeA = slotStartTime(a) ?? ''
    const timeB = slotStartTime(b) ?? ''
    return timeA.localeCompare(timeB)
  }),
)

const groupKey = (booking: BookingReadWithSlot): string => {
  switch (activeGrouping.value) {
    case 'date':
      return slotDate(booking) ?? '__none__'
    case 'event':
      return eventName(booking) ?? '__none__'
    case 'location':
      return slotLocation(booking) ?? '__none__'
    default:
      return '__all__'
  }
}

const groupLabel = (key: string): string => {
  if (key === '__all__') return ''
  if (key === '__none__') {
    switch (activeGrouping.value) {
      case 'date':
        return t('duties.bookings.noDate')
      case 'event':
        return t('duties.bookings.noEvent')
      case 'location':
        return t('duties.bookings.noLocation')
      default:
        return ''
    }
  }
  if (activeGrouping.value === 'date') return formatGroupLabel(key)
  return key
}

const groupedBookings = computed<BookingGroup[]>(() => {
  if (activeGrouping.value === 'none') {
    return [{ key: '__all__', label: '', bookings: sortedBookings.value }]
  }

  const groups = new Map<string, BookingReadWithSlot[]>()
  for (const booking of sortedBookings.value) {
    const k = groupKey(booking)
    if (!groups.has(k)) groups.set(k, [])
    groups.get(k)!.push(booking)
  }

  return Array.from(groups.entries()).map(([key, items]) => ({
    key,
    label: groupLabel(key),
    bookings: items,
  }))
})

const toISODate = (d: Date) => d.toISOString().slice(0, 10)

const formatGroupLabel = (dateStr: string) => {
  const today = toISODate(new Date())
  const tomorrow = toISODate(new Date(Date.now() + 86400000))
  const yesterday = toISODate(new Date(Date.now() - 86400000))

  if (dateStr === today) return t('duties.bookings.today')
  if (dateStr === tomorrow) return t('duties.bookings.tomorrow')
  if (dateStr === yesterday) return t('duties.bookings.yesterday')

  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString(locale.value, {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

// --- Data loading ---
const statusVariant = (status?: string) => {
  switch (status) {
    case 'confirmed':
      return 'default'
    case 'cancelled':
      return 'destructive'
    default:
      return 'outline'
  }
}

const loadBookings = async () => {
  loading.value = true
  try {
    const query: Record<string, string | number> = { limit: 200 }
    query.date_from = dateFrom.value ?? new Date().toISOString().slice(0, 10)
    if (dateTo.value) query.date_to = dateTo.value

    const response = await get<{ data: MyBookingsListResponse }>({
      url: '/bookings/me',
      query,
    })
    bookings.value = response.data.items
  } catch (error) {
    toastApiError(error)
  } finally {
    loading.value = false
  }
}

watch([dateFrom, dateTo], () => loadBookings())

const handleCancel = async (booking: BookingReadWithSlot) => {
  const confirmed = await confirmDestructive(t('duties.bookings.cancelConfirm'))
  if (!confirmed) return

  try {
    await del({ url: `/bookings/${booking.id}` })
    toast.success(t('duties.bookings.cancelSuccess'))
    await loadBookings()
  } catch (error) {
    toastApiError(error)
  }
}

const handleDismiss = async (booking: BookingReadWithSlot) => {
  try {
    await del({ url: `/bookings/${booking.id}/dismiss` })
    toast.success(t('duties.bookings.dismissSuccess'))
    await loadBookings()
  } catch (error) {
    toastApiError(error)
  }
}

// --- Display helpers ---

const slotTitle = (booking: BookingReadWithSlot) => {
  if (booking.duty_slot) return booking.duty_slot.title
  if (booking.cancelled_slot_title) return booking.cancelled_slot_title
  return t('duties.bookings.unknownSlot')
}

const slotDate = (booking: BookingReadWithSlot) => {
  if (booking.duty_slot) return booking.duty_slot.date
  if (booking.cancelled_slot_date) return booking.cancelled_slot_date
  return null
}

const slotStartTime = (booking: BookingReadWithSlot) => {
  return booking.duty_slot?.start_time ?? booking.cancelled_slot_start_time ?? null
}

const slotEndTime = (booking: BookingReadWithSlot) => {
  return booking.duty_slot?.end_time ?? booking.cancelled_slot_end_time ?? null
}

const slotLocation = (booking: BookingReadWithSlot) => {
  return booking.duty_slot?.location ?? null
}

const eventName = (booking: BookingReadWithSlot) => {
  return booking.duty_slot?.event_name ?? booking.cancelled_event_name ?? null
}

onMounted(loadBookings)
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <!-- Header -->
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div class="space-y-2">
        <h1 data-testid="page-heading" class="text-3xl font-bold">{{ t('duties.bookings.title') }}</h1>
        <p class="text-muted-foreground">{{ t('duties.bookings.subtitle') }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <!-- Grouping icon tabs -->
        <TooltipProvider :delay-duration="300">
          <div class="flex overflow-hidden rounded-md border">
            <Tooltip v-for="opt in groupingOptions" :key="opt.mode">
              <TooltipTrigger as-child>
                <Button
                  :data-testid="`btn-group-${opt.mode}`"
                  :variant="activeGrouping === opt.mode ? 'default' : 'ghost'"
                  size="sm"
                  class="rounded-none border-0"
                  @click="toggleGrouping(opt.mode)"
                >
                  <component :is="opt.icon" class="h-4 w-4" />
                  <span class="hidden sm:inline">{{ opt.label }}</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                {{ opt.label }}
              </TooltipContent>
            </Tooltip>
          </div>
        </TooltipProvider>
      </div>
    </div>

    <!-- Search & Filter -->
    <div class="flex flex-wrap items-center gap-4">
      <div class="relative flex-1">
        <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input v-model="searchQuery" data-testid="input-search" :placeholder="t('common.actions.search')" class="pl-10" />
      </div>
      <DateRangePicker
        :date-from="dateFrom"
        :date-to="dateTo"
        :marked-days="markedDays"
        :reset-label="t('duties.bookings.filters.clearDates')"
        @update:date-from="dateFrom = $event"
        @update:date-to="dateTo = $event"
        @update:visible-month="handleVisibleMonth"
      />
      <Button
        data-testid="btn-toggle-cancelled"
        :variant="showCancelled ? 'default' : 'outline'"
        size="sm"
        @click="showCancelled = !showCancelled"
      >
        <XCircle class="h-4 w-4 mr-1.5" />
        {{ t('duties.bookings.filters.showCancelled') }}
      </Button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12 text-muted-foreground">
      {{ t('common.states.loading') }}
    </div>

    <!-- Empty -->
    <div v-else-if="sortedBookings.length === 0" class="text-center py-12 text-muted-foreground">
      {{ t('duties.bookings.empty') }}
    </div>

    <!-- Bookings (grouped or flat) -->
    <div v-else class="space-y-8">
      <section v-for="group in groupedBookings" :key="group.key">
        <!-- Group header (only when grouping is active) -->
        <div v-if="group.label" class="flex items-center gap-3 mb-4">
          <h2 class="text-lg font-semibold truncate min-w-0 max-w-sm" :title="group.label">
            {{ group.label }}
          </h2>
          <Separator class="flex-1" />
          <span class="text-sm text-muted-foreground whitespace-nowrap">
            {{ group.bookings.length }}
          </span>
        </div>

        <!-- Bookings grid -->
        <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          <Card
            v-for="booking in group.bookings"
            :key="booking.id"
            :class="[booking.status === 'cancelled' ? 'opacity-75 border-destructive/30' : '']"
          >
            <CardHeader class="pb-3">
              <div class="flex items-start justify-between gap-2 min-w-0">
                <div class="min-w-0">
                  <!-- Use event name as title for active bookings; fall back to slot title for cancelled -->
                  <CardTitle
                    class="text-lg truncate"
                    :title="eventName(booking) ?? slotTitle(booking)"
                  >
                    {{ eventName(booking) ?? slotTitle(booking) }}
                  </CardTitle>
                </div>
                <Badge :variant="statusVariant(booking.status)" class="shrink-0">
                  {{ t(`duties.bookings.statuses.${booking.status ?? 'confirmed'}`) }}
                </Badge>
              </div>
            </CardHeader>
            <CardContent class="grow-1 flex flex-col">
              <div class="space-y-2 text-sm text-muted-foreground">
                <!-- Date -->
                <div v-if="slotDate(booking)" class="flex items-center gap-1.5">
                  <Calendar class="h-3.5 w-3.5" />
                  {{ formatDateLabel(slotDate(booking)!) }}
                </div>

                <!-- Time -->
                <div
                  v-if="slotStartTime(booking) || slotEndTime(booking)"
                  class="flex items-center gap-1.5"
                >
                  <Clock class="h-3.5 w-3.5" />
                  {{ formatTime(slotStartTime(booking)) }}
                  <template v-if="slotStartTime(booking) && slotEndTime(booking)"> - </template>
                  {{ formatTime(slotEndTime(booking)) }}
                </div>

                <!-- Location -->
                <div v-if="slotLocation(booking)" class="flex items-center gap-1.5">
                  <MapPin class="h-3.5 w-3.5" />
                  {{ slotLocation(booking) }}
                </div>
              </div>

              <!-- Cancellation reason -->
              <div
                v-if="booking.status === 'cancelled' && booking.cancellation_reason"
                class="mt-3"
              >
                <Separator class="mb-3" />
                <div class="flex gap-2 rounded-md bg-destructive/10 p-2.5 text-sm">
                  <AlertCircle class="h-4 w-4 text-destructive shrink-0 mt-0.5" />
                  <div>
                    <p class="font-medium text-destructive">
                      {{ t('duties.bookings.cancellationReason') }}
                    </p>
                    <p class="text-muted-foreground mt-0.5">
                      {{ booking.cancellation_reason }}
                    </p>
                  </div>
                </div>
              </div>

              <!-- Slot deleted notice -->
              <div v-else-if="booking.status === 'cancelled' && !booking.duty_slot_id" class="mt-3">
                <Separator class="mb-3" />
                <p class="text-xs text-muted-foreground italic">
                  {{ t('duties.bookings.slotDeleted') }}
                </p>
              </div>

              <!-- Spacer -->
              <div class="flex-1"></div>

              <!-- Action buttons -->
              <div class="mt-4 flex items-center gap-2">
                <!-- Detail button (only for active slots) -->
                <Button
                  v-if="booking.duty_slot"
                  variant="outline"
                  size="sm"
                  @click="openBookingDetail(booking)"
                >
                  {{ t('duties.dutySlots.detail.openDetails') }}
                </Button>

                <div class="flex-1" />

                <!-- Cancel button -->
                <TooltipProvider v-if="booking.status === 'confirmed'" :delay-duration="300">
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <Button
                        variant="ghost"
                        size="icon"
                        class="h-8 w-8 text-destructive hover:text-destructive"
                        @click="handleCancel(booking)"
                      >
                        <Trash2 class="h-4 w-4" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                      {{ t('duties.bookings.cancel') }}
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>

                <!-- Dismiss button for cancelled bookings -->
                <Button
                  v-if="booking.status === 'cancelled'"
                  variant="ghost"
                  size="sm"
                  class="text-muted-foreground"
                  @click="handleDismiss(booking)"
                >
                  {{ t('duties.bookings.dismiss') }}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>
    </div>

  </div>
</template>
