<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { Check, ChevronRight } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useFormatters } from '@/composables/useFormatters'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Skeleton } from '@/components/ui/skeleton'

import LocationDescription from '@/components/locations/LocationDescription.vue'
import ShiftDetailDialog from '@/components/tasks/ShiftDetailDialog.vue'

import type { LocationRead, LocationShiftRead, VenueLocationStat } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { STAFFING_CLASSES, staffingLabelKey, staffingStatus } from '@/lib/venue-map'

/**
 * One place on one day: how well it is staffed, its description, then that
 * day's shifts there, each bookable in one tap. Tapping a shift row opens the
 * full `ShiftDetailDialog` on top.
 *
 * The map shows this in its side panel on a wide screen and inside
 * `VenueLocationSheet` (a bottom drawer) on a phone. Shifts load while
 * `active` is on. Emits `booked` after any booking change, so the map can
 * refresh its staffing and "my shifts" highlight.
 */
const props = withDefaults(
  defineProps<{
    location: LocationRead
    /** The day shown on the map, `YYYY-MM-DD`. */
    day: string
    /** That day's numbers for the place, or nothing when it has no shifts. */
    stat?: VenueLocationStat | null
    /** Load the shifts (an open sheet, a shown panel). */
    active?: boolean
    /** Show the place's name as a heading (the sheet has its own title). */
    showHeading?: boolean
  }>(),
  { stat: null, active: true, showHeading: true },
)

const emit = defineEmits<{
  booked: []
}>()

const { t } = useI18n()
const { formatTimeRange, formatDateLabel } = useFormatters()
const { get, post } = useAuthenticatedClient()

const shifts = ref<LocationShiftRead[]>([])
const loading = ref(false)
const loadError = ref(false)
const bookingId = ref<string | null>(null)

const detailShiftId = ref<string | null>(null)
const detailOpen = ref(false)

const dayLabel = computed(() =>
  formatDateLabel(props.day, { weekday: 'long', day: 'numeric', month: 'long' }),
)

const status = computed(() => staffingStatus(props.stat))
const statusClasses = computed(() => STAFFING_CLASSES[status.value])
const openSlots = computed(() =>
  props.stat ? Math.max(0, props.stat.capacity - props.stat.booked) : 0,
)
const fillPercent = computed(() => {
  const stat = props.stat
  if (!stat || stat.capacity <= 0) return 0
  return Math.min(100, Math.round((stat.booked / stat.capacity) * 100))
})

// A response for a location or day the panel has since moved away from is dropped.
let requestSeq = 0
// Which location and day `shifts` belongs to. A reload of the same pair (after a
// booking) keeps the list on screen; a new pair clears it, so another place's
// rows and their Book buttons never show under this one's title.
let shownKey = ''

async function loadShifts() {
  const location = props.location
  const key = `${location.id}|${props.day}`
  if (key !== shownKey) {
    shifts.value = []
    shownKey = key
  }
  const seq = ++requestSeq
  loading.value = true
  loadError.value = false
  try {
    const res = await get<{ data: LocationShiftRead[] }>({
      url: `/locations/${location.id}/shifts`,
      query: { on: props.day },
    })
    if (seq === requestSeq) shifts.value = res.data
  } catch {
    if (seq === requestSeq) {
      shifts.value = []
      loadError.value = true
    }
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

watch(
  () => [props.active, props.location.id, props.day] as const,
  ([isActive]) => {
    if (isActive) void loadShifts()
  },
  { immediate: true },
)

const isFull = (shift: LocationShiftRead) => (shift.current_bookings ?? 0) >= shift.max_bookings

const canBook = (shift: LocationShiftRead) => !shift.is_booked_by_me && !isFull(shift)

function shiftChipClass(shift: LocationShiftRead) {
  const s = staffingStatus({ booked: shift.current_bookings ?? 0, capacity: shift.max_bookings })
  return STAFFING_CLASSES[s].chip
}

async function book(shift: LocationShiftRead) {
  if (bookingId.value) return
  bookingId.value = shift.id
  try {
    await post({ url: '/bookings/', body: { shift_id: shift.id } })
    toast.success(t('duties.bookings.bookSuccess'))
    emit('booked')
    await loadShifts()
  } catch (error) {
    toastApiError(error)
  } finally {
    bookingId.value = null
  }
}

function openShift(shift: LocationShiftRead) {
  detailShiftId.value = shift.id
  detailOpen.value = true
}

function onBookingUpdated() {
  emit('booked')
  void loadShifts()
}
</script>

<template>
  <div class="space-y-4" data-testid="location-details">
    <div class="space-y-1">
      <p
        class="flex items-center gap-1.5 text-xs font-medium tracking-wide uppercase"
        :class="statusClasses.text"
        data-testid="location-status"
      >
        <span class="size-2 rounded-full" :class="statusClasses.bg" aria-hidden="true" />
        {{ t(staffingLabelKey(status)) }}
      </p>
      <h2
        v-if="showHeading"
        class="text-xl leading-tight font-semibold tracking-tight outline-none"
        tabindex="-1"
        data-testid="location-sheet-title"
      >
        {{ location.name }}
      </h2>
    </div>

    <LocationDescription :location="location" />

    <!-- That day at a glance -->
    <div v-if="stat && stat.capacity > 0" class="bg-muted/50 space-y-2 rounded-lg border p-3">
      <div class="flex items-baseline justify-between gap-2">
        <p class="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          {{ t('venueMap.panel.staffedOn', { day: dayLabel }) }}
        </p>
        <span
          class="rounded-full border px-2 py-0.5 text-[13px] font-semibold tabular-nums"
          :class="statusClasses.chip"
          data-testid="location-summary-count"
        >
          {{ stat.booked }}/{{ stat.capacity }}
        </span>
      </div>
      <div
        class="bg-muted h-1.5 overflow-hidden rounded-full"
        role="progressbar"
        :aria-valuenow="stat.booked"
        aria-valuemin="0"
        :aria-valuemax="stat.capacity"
        :aria-label="t('venueMap.panel.staffedOn', { day: dayLabel })"
      >
        <div
          class="h-full rounded-full transition-[width]"
          :class="statusClasses.bg"
          :style="{ width: `${fillPercent}%` }"
        />
      </div>
      <p class="text-foreground/75 text-[13px]">
        {{
          openSlots > 0
            ? t('venueMap.panel.openSlots', { count: openSlots }, openSlots)
            : t('venueMap.panel.allTaken')
        }}
      </p>
    </div>

    <section class="space-y-2" :aria-busy="loading || undefined">
      <h3 class="text-muted-foreground text-xs font-medium tracking-wide uppercase">
        {{ t('venueMap.sheet.shiftsOn', { day: dayLabel }) }}
      </h3>

      <div v-if="loading && shifts.length === 0" class="space-y-2">
        <Skeleton class="h-14 w-full" />
        <Skeleton class="h-14 w-full" />
      </div>
      <p v-else-if="loadError" class="text-destructive text-sm" role="alert">
        {{ t('venueMap.sheet.loadError') }}
      </p>
      <p
        v-else-if="shifts.length === 0"
        class="text-muted-foreground py-4 text-center text-sm"
        data-testid="location-sheet-empty"
      >
        {{ t('venueMap.sheet.noShifts') }}
      </p>

      <ul v-else class="space-y-1.5" data-testid="location-sheet-shifts">
        <li
          v-for="shift in shifts"
          :key="shift.id"
          class="flex items-center gap-2 rounded-lg border pr-2"
          :class="shift.is_booked_by_me ? 'border-primary/40 bg-primary/5' : 'bg-card'"
          :data-testid="`sheet-shift-${shift.id}`"
        >
          <!--
            The row opens the shift; the booking button sits beside it, not
            inside, so the two never share a click.
          -->
          <button
            type="button"
            class="hover:bg-muted/50 focus-visible:ring-ring/50 flex min-w-0 flex-1 items-center gap-2 rounded-l-lg px-3 py-2 text-left outline-none focus-visible:ring-[3px]"
            @click="openShift(shift)"
          >
            <span class="min-w-0 flex-1">
              <span class="block text-sm font-medium tabular-nums">
                {{ formatTimeRange(shift.start_time, shift.end_time) }}
              </span>
              <span class="text-foreground/75 block truncate text-[13px]">
                {{ shift.task_name
                }}<template v-if="shift.title && shift.title !== shift.task_name">
                  · {{ shift.title }}</template
                >
              </span>
            </span>
            <span
              class="shrink-0 rounded-full border px-2 py-0.5 text-[13px] font-semibold tabular-nums"
              :class="shiftChipClass(shift)"
              :aria-label="
                t('venueMap.panel.bookedOf', {
                  booked: shift.current_bookings ?? 0,
                  max: shift.max_bookings,
                })
              "
            >
              {{ shift.current_bookings ?? 0 }}/{{ shift.max_bookings }}
            </span>
            <ChevronRight class="text-muted-foreground size-4 shrink-0" />
          </button>

          <Badge
            v-if="shift.is_booked_by_me"
            variant="secondary"
            class="shrink-0"
            :data-testid="`sheet-booked-${shift.id}`"
          >
            <Check />
            {{ t('venueMap.sheet.booked') }}
          </Badge>
          <span v-else-if="isFull(shift)" class="text-foreground/75 shrink-0 text-[13px]">
            {{ t('venueMap.sheet.full') }}
          </span>
          <Button
            v-else-if="canBook(shift)"
            size="sm"
            class="h-8 shrink-0"
            :disabled="!!bookingId"
            :aria-label="
              t('venueMap.sheet.bookShift', {
                time: formatTimeRange(shift.start_time, shift.end_time),
              })
            "
            :data-testid="`sheet-book-${shift.id}`"
            @click="book(shift)"
          >
            {{ bookingId === shift.id ? t('venueMap.sheet.booking') : t('venueMap.sheet.book') }}
          </Button>
        </li>
      </ul>
    </section>

    <ShiftDetailDialog
      v-model:open="detailOpen"
      :shift-id="detailShiftId"
      priority
      @booking-updated="onBookingUpdated"
    />
  </div>
</template>
