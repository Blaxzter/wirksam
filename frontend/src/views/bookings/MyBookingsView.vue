<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  MapPin,
  Search,
  Ticket,
  XCircle,
} from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useFormatters } from '@/composables/useFormatters'
import { useMyVoucherAccount } from '@/composables/useMyVoucherAccount'

import Button from '@/components/ui/button/Button.vue'
import { DateRangePicker } from '@/components/ui/date-range-picker'
import Input from '@/components/ui/input/Input.vue'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import Separator from '@/components/ui/separator/Separator.vue'
import { Switch } from '@/components/ui/switch'

import MyHoursCard from '@/components/bookings/MyHoursCard.vue'
import HintTooltip from '@/components/utils/HintTooltip.vue'
import MyVouchersCard from '@/components/vouchers/MyVouchersCard.vue'
import VoucherCodeDialog from '@/components/vouchers/VoucherCodeDialog.vue'

import type { BookingReadWithShift, MyBookingsListResponse } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { shiftHasEnded } from '@/lib/shift-time'
import { vouchersByBooking } from '@/lib/vouchers'

/**
 * "My bookings": the volunteer's hours and vouchers in the selected event on
 * top, then every shift they booked there as a card that opens the booking
 * (where it can be handed back). The list reads by date, or grouped by task
 * or by place; on a phone that choice sits in the filter button with the
 * dates and "cancelled", so the search keeps its width.
 */
const { t } = useI18n()
const { formatDateLabel, formatTimeRange } = useFormatters()
const { get, delete: del } = useAuthenticatedClient()
const route = useRoute()
const authStore = useAuthStore()

const bookings = ref<BookingReadWithShift[]>([])
const loading = ref(false)

// --- Hours and vouchers ---

const {
  account: voucherAccount,
  eventId: voucherEventId,
  visible: vouchersVisible,
  canShowCode,
  isExpired: eventExpired,
  reload: reloadVouchers,
} = useMyVoucherAccount()
const codeOpen = ref(false)
/** What each booking earns, for its "+2 vouchers". */
const earnedByBooking = computed(() => vouchersByBooking(voucherAccount.value?.shifts ?? []))

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

/**
 * The phone's filter button names the date range, short: on a 375 px screen
 * the search needs the room (it was squashed down to "Suchen.").
 */
const shortDateLabel = computed(() => {
  const short = (date: string) => formatDateLabel(date, { day: 'numeric', month: 'short' })
  if (!dateFrom.value) return t('duties.tasks.filters.fromToday')
  if (!dateTo.value || dateTo.value === dateFrom.value)
    return t('duties.tasks.filters.fromDate', { date: short(dateFrom.value) })
  return `${short(dateFrom.value)} – ${short(dateTo.value)}`
})

/** The button's name says what the dot shows, too: cancelled bookings are in the list. */
const filtersButtonLabel = computed(() => {
  const label = `${t('duties.tasks.filters.title')}: ${shortDateLabel.value}`
  return showCancelled.value ? `${label}, ${t('duties.bookings.filters.cancelledShown')}` : label
})

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

// --- Arrangement (remembered in this browser) ---

/** By date is the plain list in time order; by task and by place group it. */
type GroupMode = 'date' | 'task' | 'location'
const STORAGE_KEY = 'wirksam:bookings:groupBy'
const GROUP_MODES: GroupMode[] = ['date', 'task', 'location']

function readGrouping(): GroupMode {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    // An older "none" (the plain list) or "date" (headed by day) is now by date.
    return stored === 'task' || stored === 'location' ? stored : 'date'
  } catch {
    return 'date'
  }
}

const activeGrouping = ref<GroupMode>(readGrouping())

watch(activeGrouping, (v) => {
  try {
    localStorage.setItem(STORAGE_KEY, v)
  } catch {
    // Private mode or blocked storage: the choice lasts until the page closes.
  }
})

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

const groupKey = (booking: BookingReadWithShift): string =>
  (activeGrouping.value === 'task' ? taskName(booking) : slotLocation(booking)) ?? '__none__'

const groupLabel = (key: string): string => {
  if (key !== '__none__') return key
  return activeGrouping.value === 'task'
    ? t('duties.bookings.noTask')
    : t('duties.bookings.noLocation')
}

const groupedBookings = computed<BookingGroup[]>(() => {
  if (activeGrouping.value === 'date') {
    return [{ key: '__all__', label: '', bookings: sortedBookings.value }]
  }

  const groups = new Map<string, BookingReadWithShift[]>()
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

// --- Data loading ---

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

const taskName = (booking: BookingReadWithShift) => {
  return booking.shift?.task_name ?? booking.cancelled_task_name ?? null
}

/** "Sat, 18 July · 17:00 – 20:00", and "· over" once the shift has ended. */
const whenLine = (booking: BookingReadWithShift) => {
  const date = slotDate(booking)
  const parts: string[] = []
  if (date) parts.push(formatDateLabel(date, { weekday: 'short', day: 'numeric', month: 'long' }))
  const times = formatTimeRange(slotStartTime(booking), slotEndTime(booking))
  if (times) parts.push(times)
  if (
    booking.status === 'confirmed' &&
    date &&
    shiftHasEnded(date, slotStartTime(booking), slotEndTime(booking), booking.shift?.event_timezone)
  ) {
    parts.push(t('duties.bookings.over'))
  }
  return parts.join(' · ')
}

const isCancelled = (booking: BookingReadWithShift) => booking.status === 'cancelled'

const pillClass = (booking: BookingReadWithShift) =>
  isCancelled(booking) ? 'bg-destructive/10 text-destructive' : 'bg-primary/12 text-primary'

const chipClass =
  'inline-flex max-w-full min-w-0 items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-semibold text-foreground/80'

onMounted(loadBookings)
</script>

<template>
  <div class="@container mx-auto flex max-w-[70rem] flex-col gap-4 sm:gap-6">
    <!-- Header: what this is and whose, and how the list is arranged -->
    <header class="flex flex-wrap items-end justify-between gap-4">
      <div class="min-w-0">
        <h1
          data-testid="page-heading"
          class="text-[1.625rem] leading-tight font-bold tracking-tight sm:text-[2rem]"
        >
          {{ t('duties.bookings.title') }}
        </h1>
        <p class="mt-0.5 text-sm text-muted-foreground sm:mt-1 sm:text-[15px]">
          {{ authStore.selectedEvent?.name ?? t('duties.bookings.subtitle') }}
        </p>
      </div>
      <div
        role="group"
        :aria-label="t('duties.bookings.arrange')"
        class="hidden rounded-xl border bg-card p-[3px] sm:flex"
      >
        <button
          v-for="mode in GROUP_MODES"
          :key="mode"
          type="button"
          :aria-pressed="activeGrouping === mode"
          class="min-h-[38px] rounded-[9px] px-3.5 text-sm outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          :class="
            activeGrouping === mode
              ? 'bg-muted font-semibold text-foreground'
              : 'text-muted-foreground hover:text-foreground'
          "
          :data-testid="`btn-event-${mode}`"
          @click="activeGrouping = mode"
        >
          {{ t(`duties.bookings.groupBy.${mode}`) }}
        </button>
      </div>
    </header>

    <!--
      Hours and vouchers. Tiles side by side on a phone, vouchers first; full
      cards from @2xl, hours first. Either one alone takes the whole row.
    -->
    <div class="grid grid-cols-2 gap-3 @2xl:gap-6">
      <MyVouchersCard
        v-if="vouchersVisible && voucherAccount && voucherEventId"
        class="only:col-span-2 @2xl:order-2"
        :account="voucherAccount"
        :event-id="voucherEventId"
        :expired="eventExpired"
        :can-show-code="canShowCode"
        @show-code="codeOpen = true"
      />
      <MyHoursCard class="only:col-span-2 @2xl:order-1" />
    </div>

    <!--
      Search & Filter. Phones: the search and one filter button share a row,
      the date range, "cancelled" and the arrangement behind it. Wider: the
      search takes what the two controls leave, and they wrap below it once it
      would drop under 20rem.
    -->
    <div class="flex flex-wrap items-center gap-2 sm:gap-4" data-testid="bookings-filter-row">
      <div class="relative min-w-0 flex-1 sm:basis-80">
        <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          v-model="searchQuery"
          data-testid="input-search"
          :placeholder="t('common.actions.search')"
          class="h-11 pl-10"
        />
      </div>

      <Popover>
        <PopoverTrigger as-child>
          <Button
            variant="outline"
            class="h-11 max-w-36 shrink-0 gap-1.5 px-3 sm:hidden"
            :aria-label="filtersButtonLabel"
            data-testid="btn-bookings-filters"
          >
            <span class="truncate">{{ shortDateLabel }}</span>
            <span
              v-if="showCancelled"
              class="size-1.5 shrink-0 rounded-full bg-primary"
              aria-hidden="true"
            />
            <ChevronDown class="size-4 shrink-0" aria-hidden="true" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" class="w-72 space-y-4" data-testid="bookings-filters">
          <h4 class="text-sm font-medium">{{ t('duties.tasks.filters.title') }}</h4>
          <DateRangePicker
            :date-from="dateFrom"
            :date-to="dateTo"
            :marked-days="markedDays"
            :reset-label="t('duties.bookings.filters.clearDates')"
            @update:date-from="dateFrom = $event"
            @update:date-to="dateTo = $event"
            @update:visible-month="handleVisibleMonth"
          />
          <div class="flex items-center justify-between gap-3">
            <Label for="bookings-show-cancelled" class="cursor-pointer text-sm font-normal">
              {{ t('duties.bookings.filters.includeCancelled') }}
            </Label>
            <Switch
              id="bookings-show-cancelled"
              data-testid="switch-show-cancelled"
              :model-value="showCancelled"
              @update:model-value="showCancelled = $event"
            />
          </div>
          <div class="space-y-2">
            <p id="bookings-arrange-label" class="text-sm">{{ t('duties.bookings.arrange') }}</p>
            <div
              role="group"
              aria-labelledby="bookings-arrange-label"
              class="grid grid-cols-3 rounded-xl border bg-card p-[3px]"
            >
              <button
                v-for="mode in GROUP_MODES"
                :key="mode"
                type="button"
                :aria-pressed="activeGrouping === mode"
                class="min-h-11 rounded-[9px] px-2 text-sm outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                :class="
                  activeGrouping === mode
                    ? 'bg-muted font-semibold text-foreground'
                    : 'text-muted-foreground'
                "
                :data-testid="`btn-arrange-${mode}`"
                @click="activeGrouping = mode"
              >
                {{ t(`duties.bookings.groupByShort.${mode}`) }}
              </button>
            </div>
          </div>
        </PopoverContent>
      </Popover>

      <!-- One height for the row, the search's: the date picker's trigger is its own -->
      <div class="hidden sm:contents [&>button]:h-11 [&>button]:px-3.5">
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
          @click="showCancelled = !showCancelled"
        >
          <XCircle class="h-4 w-4 mr-1.5" />
          {{ t('duties.bookings.filters.showCancelled') }}
        </Button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12 text-muted-foreground">
      {{ t('common.states.loading') }}
    </div>

    <!-- Empty -->
    <div v-else-if="sortedBookings.length === 0" class="text-center py-12 text-muted-foreground">
      {{ t('duties.bookings.empty') }}
    </div>

    <!-- Bookings, in time order or grouped by task or place -->
    <div v-else class="space-y-8">
      <section v-for="group in groupedBookings" :key="group.key">
        <div v-if="group.label" class="mb-3 flex items-center gap-3 sm:mb-4">
          <HintTooltip :label="group.label">
            <h2 class="min-w-0 max-w-sm truncate text-lg font-semibold">
              {{ group.label }}
            </h2>
          </HintTooltip>
          <Separator class="flex-1" />
          <span class="whitespace-nowrap text-sm text-muted-foreground">
            {{ group.bookings.length }}
          </span>
        </div>

        <ul class="grid gap-2.5 sm:grid-cols-[repeat(auto-fill,minmax(280px,1fr))] sm:gap-4">
          <li v-for="booking in group.bookings" :key="booking.id" class="min-w-0">
            <!--
              One card per booking. The task's name is the link to the booking,
              stretched over the whole card; only "Remove" on a cancelled one
              sits above it. A phone puts the day first, behind a coloured bar;
              wider, the name leads with the status beside it.
            -->
            <article
              data-testid="booking-card"
              class="relative flex h-full gap-3 rounded-2xl border bg-card px-4 py-3.5 text-card-foreground transition-colors sm:rounded-[18px] sm:px-5 sm:py-[18px]"
              :class="[
                booking.shift ? 'hover:bg-muted/30' : '',
                isCancelled(booking) ? 'border-destructive/30' : '',
              ]"
            >
              <span
                class="w-1 shrink-0 rounded-full sm:hidden"
                :class="isCancelled(booking) ? 'bg-destructive/60' : 'bg-primary'"
                aria-hidden="true"
              />
              <div class="flex min-w-0 flex-1 flex-col gap-0.5 sm:gap-2">
                <div class="flex items-start justify-between gap-2 sm:order-first">
                  <h3
                    class="min-w-0 text-base leading-snug font-semibold break-words sm:text-lg sm:font-bold"
                  >
                    <RouterLink
                      v-if="booking.shift"
                      :to="{ name: 'booking-detail', params: { bookingId: booking.id } }"
                      class="rounded-sm outline-none after:absolute after:inset-0 after:rounded-[inherit] focus-visible:after:ring-[3px] focus-visible:after:ring-ring/50"
                    >
                      {{ taskName(booking) ?? slotTitle(booking) }}
                    </RouterLink>
                    <template v-else>{{ taskName(booking) ?? slotTitle(booking) }}</template>
                  </h3>
                  <span
                    class="hidden min-h-[22px] shrink-0 items-center rounded-full px-2 text-xs font-bold whitespace-nowrap sm:inline-flex"
                    :class="pillClass(booking)"
                  >
                    {{ t(`duties.bookings.statuses.${booking.status ?? 'confirmed'}`) }}
                  </span>
                </div>

                <p
                  v-if="whenLine(booking)"
                  class="order-first text-[13px] text-muted-foreground tabular-nums sm:order-none sm:text-sm"
                >
                  {{ whenLine(booking) }}
                </p>

                <div class="mt-1.5 flex flex-wrap items-center gap-1.5 sm:mt-0">
                  <span
                    class="inline-flex min-h-[22px] items-center rounded-full px-2 text-xs font-bold sm:hidden"
                    :class="pillClass(booking)"
                  >
                    {{ t(`duties.bookings.statuses.${booking.status ?? 'confirmed'}`) }}
                  </span>
                  <span
                    v-if="!isCancelled(booking) && earnedByBooking.get(booking.id)"
                    :class="chipClass"
                    data-testid="booking-card-vouchers"
                  >
                    <Ticket class="size-3 shrink-0" aria-hidden="true" />
                    {{
                      t(
                        'vouchers.bookingChip',
                        { n: earnedByBooking.get(booking.id) },
                        earnedByBooking.get(booking.id) ?? 0,
                      )
                    }}
                  </span>
                  <span v-if="slotLocation(booking)" :class="chipClass">
                    <MapPin class="size-3 shrink-0" aria-hidden="true" />
                    <span class="truncate">{{ slotLocation(booking) }}</span>
                  </span>
                </div>

                <!-- Why it was cancelled, or that the shift is gone -->
                <div
                  v-if="isCancelled(booking) && booking.cancellation_reason"
                  class="mt-2 flex gap-2 rounded-lg bg-destructive/10 p-2.5 text-sm"
                >
                  <AlertCircle class="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
                  <div>
                    <p class="font-medium text-destructive">
                      {{ t('duties.bookings.cancellationReason') }}
                    </p>
                    <p class="mt-0.5 text-muted-foreground">{{ booking.cancellation_reason }}</p>
                  </div>
                </div>
                <p
                  v-else-if="isCancelled(booking) && !booking.shift_id"
                  class="mt-2 text-xs text-muted-foreground italic"
                >
                  {{ t('duties.bookings.slotDeleted') }}
                </p>

                <div v-if="isCancelled(booking)" class="relative z-10 mt-2 flex justify-end">
                  <Button
                    variant="ghost"
                    size="sm"
                    class="-mr-2 -mb-1 h-9 text-muted-foreground"
                    @click="handleDismiss(booking)"
                  >
                    {{ t('duties.bookings.dismiss') }}
                  </Button>
                </div>
              </div>
              <ChevronRight
                v-if="booking.shift"
                class="size-4 shrink-0 self-center text-muted-foreground sm:hidden"
                aria-hidden="true"
              />
            </article>
          </li>
        </ul>
      </section>
    </div>

    <!-- A code redeemed while it is open changes the numbers above. -->
    <VoucherCodeDialog
      v-if="voucherEventId && !eventExpired"
      v-model:open="codeOpen"
      :event-id="voucherEventId"
      @redeemed="reloadVouchers"
    />
  </div>
</template>
