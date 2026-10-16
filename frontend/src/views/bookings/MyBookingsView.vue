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
} from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'
import { useFormatters } from '@/composables/useFormatters'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { DateRangePicker } from '@/components/ui/date-range-picker'
import Input from '@/components/ui/input/Input.vue'
import Separator from '@/components/ui/separator/Separator.vue'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

import HintTooltip from '@/components/utils/HintTooltip.vue'
import MyHoursCard from '@/components/bookings/MyHoursCard.vue'

import type { BookingReadWithShift, MyBookingsListResponse } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const { t, locale } = useI18n()
const { formatTime, formatDateLabel } = useFormatters()
const { get, delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()
const router = useRouter()
const route = useRoute()

const bookings = ref<BookingReadWithShift[]>([])
const loading = ref(false)
const hoursCard = ref<InstanceType<typeof MyHoursCard> | null>(null)

const openBookingDetail = (booking: BookingReadWithShift) => {
  router.push({ name: 'booking-detail', params: { bookingId: booking.id } })
}

// --- Filter state ---

/**
 * How far back `?range=all` reaches.
 *
 * The guided tour's "my bookings" step talks about both halves of this screen —
 * what you have promised and what you have already done — but the default view
 * only ever shows the first, because `loadBookings` falls back to today when no
 * `dateFrom` is set. A tour step can only carry a static query value, so the
 * view resolves the actual date itself and the tour just asks for "all".
 */
const HISTORY_DAYS = 120

/** Local calendar date N days back — `toISOString()` would shift it by the UTC offset. */
const isoDaysAgo = (days: number) => {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const dateFrom = ref<string | null>(route.query.range === 'all' ? isoDaysAgo(HISTORY_DAYS) : null)
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
type GroupMode = 'none' | 'date' | 'task' | 'location'
const STORAGE_KEY = 'wirksam:bookings:groupBy'
const activeGrouping = ref<GroupMode>((localStorage.getItem(STORAGE_KEY) as GroupMode) || 'none')

watch(activeGrouping, (v) => localStorage.setItem(STORAGE_KEY, v))

const groupingOptions = computed(() => [
  { mode: 'date' as const, icon: CalendarDays, label: t('duties.bookings.groupBy.date') },
  { mode: 'task' as const, icon: Layers, label: t('duties.bookings.groupBy.task') },
  { mode: 'location' as const, icon: MapPin, label: t('duties.bookings.groupBy.location') },
])

// --- Grouping logic ---
interface BookingGroup {
  key: string
  label: string
  bookings: BookingReadWithShift[]
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
      const shift = b.shift
      if (!shift) return false
      return (
        shift.title?.toLowerCase().includes(query) ||
        shift.task_name?.toLowerCase().includes(query) ||
        shift.location?.toLowerCase().includes(query)
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

const groupKey = (booking: BookingReadWithShift): string => {
  switch (activeGrouping.value) {
    case 'date':
      return slotDate(booking) ?? '__none__'
    case 'task':
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
      case 'task':
        return t('duties.bookings.noTask')
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

  const events = new Map<string, BookingReadWithShift[]>()
  for (const booking of sortedBookings.value) {
    const k = groupKey(booking)
    if (!events.has(k)) events.set(k, [])
    events.get(k)!.push(booking)
  }

  return Array.from(events.entries()).map(([key, items]) => ({
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

const handleCancel = async (booking: BookingReadWithShift) => {
  const confirmed = await confirmDestructive(t('duties.bookings.cancelConfirm'))
  if (!confirmed) return

  try {
    await del({ url: `/bookings/${booking.id}` })
    toast.success(t('duties.bookings.cancelSuccess'))
    await Promise.all([loadBookings(), hoursCard.value?.reload()])
  } catch (error) {
    toastApiError(error)
  }
}

const handleDismiss = async (booking: BookingReadWithShift) => {
  try {
    await del({ url: `/bookings/${booking.id}/dismiss` })
    toast.success(t('duties.bookings.dismissSuccess'))
    await loadBookings()
  } catch (error) {
    toastApiError(error)
  }
}

// --- Display helpers ---

const slotTitle = (booking: BookingReadWithShift) => {
  if (booking.shift) return booking.shift.title
  if (booking.cancelled_shift_title) return booking.cancelled_shift_title
  return t('duties.bookings.unknownShift')
}

const slotDate = (booking: BookingReadWithShift) => {
  if (booking.shift) return booking.shift.date
  if (booking.cancelled_shift_date) return booking.cancelled_shift_date
  return null
}

const slotStartTime = (booking: BookingReadWithShift) => {
  return booking.shift?.start_time ?? booking.cancelled_shift_start_time ?? null
}

const slotEndTime = (booking: BookingReadWithShift) => {
  return booking.shift?.end_time ?? booking.cancelled_shift_end_time ?? null
}

const slotLocation = (booking: BookingReadWithShift) => {
  return booking.shift?.location ?? null
}

const eventName = (booking: BookingReadWithShift) => {
  return booking.shift?.task_name ?? booking.cancelled_task_name ?? null
}

onMounted(loadBookings)
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <!-- Header -->
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div class="space-y-2">
        <h1 data-testid="page-heading" class="text-2xl sm:text-3xl font-bold">
          {{ t('duties.bookings.title') }}
        </h1>
        <p class="text-muted-foreground">{{ t('duties.bookings.subtitle') }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <!-- Grouping icon tabs -->
        <TooltipProvider :delay-duration="300">
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            :model-value="activeGrouping === 'none' ? '' : activeGrouping"
            @update:model-value="(v) => (activeGrouping = (v as GroupMode) || 'none')"
          >
            <Tooltip v-for="opt in groupingOptions" :key="opt.mode">
              <TooltipTrigger as-child>
                <ToggleGroupItem :value="opt.mode" :data-testid="`btn-event-${opt.mode}`">
                  <component :is="opt.icon" class="h-4 w-4" />
                  <span class="hidden sm:inline">{{ opt.label }}</span>
                </ToggleGroupItem>
              </TooltipTrigger>
              <TooltipContent>
                {{ opt.label }}
              </TooltipContent>
            </Tooltip>
          </ToggleGroup>
        </TooltipProvider>
      </div>
    </div>

    <MyHoursCard ref="hoursCard" />

    <!-- Search & Filter -->
    <div class="flex flex-wrap items-center gap-4">
      <div class="relative flex-1">
        <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          v-model="searchQuery"
          data-testid="input-search"
          :placeholder="t('common.actions.search')"
          class="pl-10"
        />
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
      <section v-for="event in groupedBookings" :key="event.key">
        <!-- Group header (only when grouping is active) -->
        <div v-if="event.label" class="flex items-center gap-3 mb-4">
          <HintTooltip :label="event.label">
            <h2 class="text-lg font-semibold truncate min-w-0 max-w-sm">
              {{ event.label }}
            </h2>
          </HintTooltip>
          <Separator class="flex-1" />
          <span class="text-sm text-muted-foreground whitespace-nowrap">
            {{ event.bookings.length }}
          </span>
        </div>

        <!-- Bookings grid -->
        <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          <Card
            v-for="booking in event.bookings"
            :key="booking.id"
            data-testid="booking-card"
            :class="[booking.status === 'cancelled' ? 'opacity-75 border-destructive/30' : '']"
          >
            <CardHeader class="pb-3">
              <div class="flex items-start justify-between gap-2 min-w-0">
                <div class="min-w-0">
                  <!-- Use task name as title for active bookings; fall back to shift title for cancelled -->
                  <HintTooltip :label="eventName(booking) ?? slotTitle(booking)">
                    <CardTitle class="text-lg truncate">
                      {{ eventName(booking) ?? slotTitle(booking) }}
                    </CardTitle>
                  </HintTooltip>
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

              <!-- Shift deleted notice -->
              <div v-else-if="booking.status === 'cancelled' && !booking.shift_id" class="mt-3">
                <Separator class="mb-3" />
                <p class="text-xs text-muted-foreground italic">
                  {{ t('duties.bookings.slotDeleted') }}
                </p>
              </div>

              <!-- Spacer -->
              <div class="flex-1"></div>

              <!-- Action buttons -->
              <div class="mt-4 flex items-center gap-2">
                <!-- Detail button (only for active shifts) -->
                <Button
                  v-if="booking.shift"
                  variant="outline"
                  size="sm"
                  @click="openBookingDetail(booking)"
                >
                  {{ t('duties.shifts.detail.openDetails') }}
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
                        :aria-label="t('duties.bookings.cancel')"
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
