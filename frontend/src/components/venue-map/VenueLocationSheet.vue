<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { Check, ChevronRight, Users } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useFormatters } from '@/composables/useFormatters'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'
import Separator from '@/components/ui/separator/Separator.vue'
import { Skeleton } from '@/components/ui/skeleton'

import LocationDescription from '@/components/locations/LocationDescription.vue'
import ShiftDetailDialog from '@/components/tasks/ShiftDetailDialog.vue'

import type { LocationRead, LocationShiftRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

/**
 * What happens at one place on the map on one day: the location's description,
 * then that day's shifts there, each bookable in one tap.
 *
 * A bottom drawer on a phone (it is a `ResponsiveDialog`), a centred dialog on
 * a desktop. Tapping a shift row opens the full `ShiftDetailDialog` on top.
 * Emits `booked` after any booking change, so the map can refresh its "my
 * shifts" highlight.
 */
const props = defineProps<{
  location: LocationRead | null
  /** The day shown on the map, `YYYY-MM-DD`. */
  day: string
}>()

const open = defineModel<boolean>('open', { default: false })

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

// A response for a location or day the sheet has since moved away from is dropped.
let requestSeq = 0
// Which location and day `shifts` belongs to. A reload of the same pair (after a
// booking) keeps the list on screen; a new pair clears it, so another place's
// rows and their Book buttons never show under this one's title.
let shownKey = ''

async function loadShifts() {
  const location = props.location
  if (!location) return
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
  () => [open.value, props.location?.id, props.day] as const,
  ([isOpen]) => {
    if (isOpen) void loadShifts()
  },
  { immediate: true },
)

const isFull = (shift: LocationShiftRead) => (shift.current_bookings ?? 0) >= shift.max_bookings

const canBook = (shift: LocationShiftRead) => !shift.is_booked_by_me && !isFull(shift)

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
  <ResponsiveDialog v-model:open="open">
    <ResponsiveDialogContent data-testid="location-sheet" dialog-class="sm:max-w-lg">
      <ResponsiveDialogHeader>
        <ResponsiveDialogTitle data-testid="location-sheet-title">
          {{ location?.name }}
        </ResponsiveDialogTitle>
        <ResponsiveDialogDescription class="sr-only">
          {{ t('venueMap.sheet.shiftsOn', { day: dayLabel }) }}
        </ResponsiveDialogDescription>
      </ResponsiveDialogHeader>

      <ResponsiveDialogBody v-if="location" class="space-y-4 pb-4">
        <LocationDescription :location="location" />

        <Separator />

        <section class="space-y-2" :aria-busy="loading || undefined">
          <h3 class="text-sm font-semibold">
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

          <ul v-else class="divide-y rounded-lg border" data-testid="location-sheet-shifts">
            <li
              v-for="shift in shifts"
              :key="shift.id"
              class="flex items-center gap-2 pr-2"
              :data-testid="`sheet-shift-${shift.id}`"
            >
              <!--
                The row opens the shift; the booking button sits beside it, not
                inside, so the two never share a click.
              -->
              <button
                type="button"
                class="hover:bg-muted/50 focus-visible:ring-ring/50 flex min-w-0 flex-1 items-center gap-2 rounded-l-lg px-3 py-2.5 text-left outline-none focus-visible:ring-[3px]"
                @click="openShift(shift)"
              >
                <span class="min-w-0 flex-1">
                  <span class="block text-sm font-medium tabular-nums">
                    {{ formatTimeRange(shift.start_time, shift.end_time) }}
                  </span>
                  <span class="text-muted-foreground block truncate text-sm">
                    {{ shift.task_name
                    }}<template v-if="shift.title && shift.title !== shift.task_name">
                      · {{ shift.title }}</template
                    >
                  </span>
                </span>
                <span class="text-muted-foreground flex shrink-0 items-center gap-1 text-xs">
                  <Users class="size-3.5" />
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
              <span v-else-if="isFull(shift)" class="text-muted-foreground shrink-0 text-xs">
                {{ t('venueMap.sheet.full') }}
              </span>
              <Button
                v-else-if="canBook(shift)"
                size="sm"
                class="h-9 shrink-0"
                :disabled="!!bookingId"
                :aria-label="
                  t('venueMap.sheet.bookShift', {
                    time: formatTimeRange(shift.start_time, shift.end_time),
                  })
                "
                :data-testid="`sheet-book-${shift.id}`"
                @click="book(shift)"
              >
                {{
                  bookingId === shift.id ? t('venueMap.sheet.booking') : t('venueMap.sheet.book')
                }}
              </Button>
            </li>
          </ul>
        </section>
      </ResponsiveDialogBody>
    </ResponsiveDialogContent>
  </ResponsiveDialog>

  <ShiftDetailDialog
    v-model:open="detailOpen"
    :shift-id="detailShiftId"
    priority
    @booking-updated="onBookingUpdated"
  />
</template>
