<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { ChevronRight, EllipsisVertical, ExternalLink, Lock, MapPin, Tag, Users } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'
import { useFormatters } from '@/composables/useFormatters'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
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

import LocationDescription from '@/components/locations/LocationDescription.vue'
import ShiftRoster from '@/components/tasks/ShiftRoster.vue'
import TeamJoinButton from '@/components/tasks/TeamJoinButton.vue'
import VenueMiniMap from '@/components/venue-map/VenueMiniMap.vue'

import type {
  BookingRead,
  LocationDetailRead,
  ShiftBookingEntry,
  ShiftRead,
} from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const props = withDefaults(
  defineProps<{
    /** Pass a full shift object (from TaskDetailView) */
    shift?: ShiftRead | null
    /** Or pass just an ID to fetch the shift (from MyBookingsView) */
    shiftId?: string | null
    taskName?: string | null
    /** The current user's booking for this shift (enables booking link) */
    myBooking?: BookingRead | null
    /** Whether to show the "View Task" navigation link (hide when already on task page) */
    showTaskLink?: boolean
    /** Stack above another open dialog (e.g. the map's location sheet). */
    priority?: boolean
    open: boolean
  }>(),
  { showTaskLink: true, priority: false },
)

const emit = defineEmits<{
  'update:open': [value: boolean]
  'booking-updated': []
  /** The user joined (or asked to join) the team the shift is reserved for. */
  'team-joined': [status: 'approved' | 'pending']
}>()

const { t } = useI18n()
const { formatTimeRange, formatDateLabel } = useFormatters()
const router = useRouter()
const { get, post, delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()
const authStore = useAuthStore()

const fetchedShift = ref<ShiftRead | null>(null)
const shiftBookings = ref<ShiftBookingEntry[]>([])
const loadingShift = ref(false)
const loadingBookings = ref(false)

const dialogOpen = computed({
  get: () => props.open,
  set: (v) => emit('update:open', v),
})

/** The resolved shift — either from props or fetched by ID */
const resolvedShift = computed(() => props.shift ?? fetchedShift.value)

/** The resolved booking — from props, or auto-detected from fetched shift bookings */
const resolvedMyBooking = computed(() => {
  if (props.myBooking) return props.myBooking
  // By id, not by email. A sandbox guest has no email address at all — the
  // seeder refuses to give them one, because `send_verify_email` short-circuits
  // on a missing one — so matching on `user_email` never matched: a demo
  // visitor was never offered *Cancel* for a shift they were on, and was
  // offered *Book* for one, which answers 409.
  //
  // `profile` rather than `user`: `profile` is the `/users/me` row and always
  // carries an id, including under the E2E `X-Test-User-Email` bypass, whose
  // hand-made session identity has a `sub` and no `id`.
  const userId = authStore.profile?.id ?? authStore.user?.id ?? null
  if (!userId || shiftBookings.value.length === 0) return null
  const entry = shiftBookings.value.find((b) => b.user_id === userId)
  if (!entry) return null
  return { id: entry.id, notes: entry.notes ?? null } as { id: string; notes: string | null }
})

// Load data when dialog opens
watch(
  () => props.open,
  async (isOpen) => {
    if (!isOpen) {
      shiftBookings.value = []
      fetchedShift.value = null
      return
    }

    // If we only have a shiftId, fetch the full shift
    const shiftId = props.shift?.id ?? props.shiftId
    if (!props.shift && props.shiftId) {
      loadingShift.value = true
      try {
        const response = await get<{ data: ShiftRead }>({
          url: `/shifts/${props.shiftId}`,
        })
        fetchedShift.value = response.data
      } catch {
        fetchedShift.value = null
      } finally {
        loadingShift.value = false
      }
    }

    // Load bookings
    if (shiftId) {
      loadingBookings.value = true
      try {
        const response = await get<{ data: ShiftBookingEntry[] }>({
          url: `/shifts/${shiftId}/bookings`,
        })
        shiftBookings.value = response.data
      } catch {
        shiftBookings.value = []
      } finally {
        loadingBookings.value = false
      }
    }
  },
)

// --- Location details ---
// Descriptions up to this length start expanded; longer ones would push the
// roster out of view, so they start folded.
const SHORT_DESCRIPTION = 280

const locationDetail = ref<LocationDetailRead | null>(null)
const locationDetailsOpen = ref(false)

const locationHasDetails = computed(() => {
  const l = locationDetail.value
  return !!(l && (l.description?.trim() || l.address || l.map_url || l.contact))
})
const locationPin = computed(() => locationDetail.value?.pins?.[0] ?? null)

watch(
  () => (props.open ? (resolvedShift.value?.location_id ?? null) : null),
  async (locationId) => {
    if (!locationId) {
      locationDetail.value = null
      return
    }
    if (locationDetail.value?.id === locationId) return
    try {
      const res = await get<{ data: LocationDetailRead }>({ url: `/locations/${locationId}` })
      // The dialog may have moved on to another shift meanwhile.
      if ((resolvedShift.value?.location_id ?? null) !== locationId) return
      locationDetail.value = res.data
      locationDetailsOpen.value = (res.data.description?.length ?? 0) < SHORT_DESCRIPTION
    } catch {
      // Non-critical — the name is still shown above.
      locationDetail.value = null
    }
  },
  { immediate: true },
)

/**
 * What the shift *is*, in the reader's terms.
 *
 * The task name is what someone recognises ("Reception"), so it leads. The
 * shift's own `title` is generated as `"<task> <HH:MM>-<HH:MM>"`, which would
 * repeat both the heading and the line under it, so it is only a fallback for
 * the callers that do not pass a task name at all.
 */
const headline = computed(
  () => props.taskName || resolvedShift.value?.title || t('duties.shifts.detail.title'),
)

const capacity = computed(() => resolvedShift.value?.max_bookings ?? 1)
const bookedCount = computed(() => resolvedShift.value?.current_bookings ?? 0)

/** "Thu, 27 Aug 2026 · 09:00 – 11:00" — the one line people actually scan for. */
const whenLine = computed(() => {
  const s = resolvedShift.value
  if (!s) return loadingShift.value ? t('common.states.loading') : (props.taskName ?? '')
  const date = formatDateLabel(s.date, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
  const time = formatTimeRange(s.start_time, s.end_time)
  return time ? `${date} · ${time}` : date
})

const isShiftFull = computed(() => bookedCount.value >= capacity.value)

/**
 * The server's own answer, from `_enrich_shift` in `api/routes/shifts.py`.
 *
 * It cannot replace `resolvedMyBooking`, which has to carry the booking id for
 * the cancel call, but it is authoritative and it arrives before the roster
 * request settles — so it is what keeps *Book shift* from being offered in the
 * window where the roster is still in flight, or came back empty on an error.
 */
const bookedByMeOnServer = computed(() => resolvedShift.value?.is_booked_by_me === true)

/** Overlaps a shift the user already holds — the server would refuse it. */
const clashesWithMine = computed(
  () => !resolvedMyBooking.value && !!resolvedShift.value?.collides_with_my_booking,
)

// The user's team status after joining from this dialog, ahead of a reload.
const joinedStatus = ref<'approved' | 'pending' | null>(null)
watch(
  () => [props.open, resolvedShift.value?.id],
  () => (joinedStatus.value = null),
)

/** Reserved for a team the user is not (yet) an approved member of. */
const lockedByTeam = computed(
  () =>
    !resolvedMyBooking.value &&
    !!resolvedShift.value?.locked_by_team &&
    joinedStatus.value !== 'approved',
)

const onTeamJoined = (status: 'approved' | 'pending') => {
  joinedStatus.value = status
  emit('team-joined', status)
}

const canBook = computed(() => {
  return (
    !resolvedMyBooking.value &&
    !bookedByMeOnServer.value &&
    !isShiftFull.value &&
    !clashesWithMine.value &&
    !lockedByTeam.value
  )
})

const hasMenuItems = computed(() => {
  return (props.showTaskLink && !!resolvedShift.value?.task_id) || !!resolvedMyBooking.value
})

const bookingInProgress = ref(false)

const handleBook = async () => {
  const shift = resolvedShift.value
  if (!shift || isShiftFull.value) return
  bookingInProgress.value = true
  try {
    await post({ url: '/bookings/', body: { shift_id: shift.id } })
    toast.success(t('duties.bookings.bookSuccess'))
    emit('booking-updated')
    dialogOpen.value = false
  } catch (error) {
    toastApiError(error)
  } finally {
    bookingInProgress.value = false
  }
}

const handleCancelBooking = async () => {
  if (!resolvedMyBooking.value) return
  const confirmed = await confirmDestructive(t('duties.bookings.cancelConfirm'))
  if (!confirmed) return
  bookingInProgress.value = true
  try {
    await del({ url: `/bookings/${resolvedMyBooking.value.id}` })
    toast.success(t('duties.bookings.cancelSuccess'))
    emit('booking-updated')
    dialogOpen.value = false
  } catch (error) {
    toastApiError(error)
  } finally {
    bookingInProgress.value = false
  }
}

const navigateToTask = () => {
  const eventId = resolvedShift.value?.task_id
  if (eventId) {
    dialogOpen.value = false
    router.push({ name: 'task-detail', params: { eventId } })
  }
}

const navigateToBooking = () => {
  const booking = resolvedMyBooking.value
  if (booking) {
    dialogOpen.value = false
    router.push({ name: 'booking-detail', params: { bookingId: booking.id } })
  }
}
</script>

<template>
  <ResponsiveDialog v-model:open="dialogOpen">
    <ResponsiveDialogContent
      data-testid="dialog-shift-detail"
      dialog-class="sm:max-w-lg"
      :priority="priority"
    >
      <ResponsiveDialogHeader>
        <div class="flex items-start justify-between gap-3">
          <ResponsiveDialogTitle data-testid="shift-detail-title">{{
            headline
          }}</ResponsiveDialogTitle>
          <Badge v-if="resolvedShift" variant="secondary" class="mt-0.5 shrink-0">
            <Users />
            {{ bookedCount }}/{{ capacity }}
          </Badge>
        </div>
        <ResponsiveDialogDescription>{{ whenLine }}</ResponsiveDialogDescription>
      </ResponsiveDialogHeader>

      <ResponsiveDialogBody class="space-y-4 pb-4">
        <p v-if="loadingShift" class="text-muted-foreground py-8 text-center text-sm">
          {{ t('common.states.loading') }}
        </p>

        <template v-else-if="resolvedShift">
          <!--
            Where and what, inline. These were two of five icon/label/value
            blocks that stacked full-width on a phone and pushed the roster —
            the part that changes — below the fold.
          -->
          <div
            v-if="resolvedShift.location || resolvedShift.category"
            class="flex flex-wrap items-center gap-x-5 gap-y-1.5 text-sm"
          >
            <span v-if="resolvedShift.location" class="flex min-w-0 items-center gap-1.5">
              <MapPin class="text-muted-foreground size-4 shrink-0" />
              <span class="truncate">{{ resolvedShift.location }}</span>
            </span>
            <span v-if="resolvedShift.category" class="flex min-w-0 items-center gap-1.5">
              <Tag class="text-muted-foreground size-4 shrink-0" />
              <span class="truncate">{{ resolvedShift.category }}</span>
            </span>
          </div>

          <p v-if="resolvedShift.description" class="text-sm whitespace-pre-line">
            {{ resolvedShift.description }}
          </p>

          <!-- The place itself: how to get there, who to ask, where on the map -->
          <Collapsible
            v-if="locationDetail && locationHasDetails"
            v-model:open="locationDetailsOpen"
            class="rounded-md border"
            data-testid="shift-location-details"
          >
            <CollapsibleTrigger as-child>
              <button
                type="button"
                class="hover:bg-muted/50 focus-visible:ring-ring/50 flex w-full items-center gap-1.5 rounded-md px-3 py-2 text-left text-sm font-medium outline-none focus-visible:ring-[3px]"
              >
                <ChevronRight
                  class="text-muted-foreground size-4 shrink-0 transition-transform"
                  :class="{ 'rotate-90': locationDetailsOpen }"
                />
                {{ t('locations.details.title') }}
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div class="px-3 pb-3">
                <LocationDescription :location="locationDetail" />
              </div>
            </CollapsibleContent>
          </Collapsible>

          <!-- Following the link leaves this dialog behind, so close it. -->
          <div
            v-if="locationDetail && locationPin"
            data-testid="shift-mini-map"
            @click="dialogOpen = false"
          >
            <VenueMiniMap
              :event-id="locationDetail.event_id"
              :pin="locationPin"
              :location-id="locationDetail.id"
            />
          </div>

          <!-- Extensibility shift: future fields (materials, protection, etc.) go here -->
          <slot name="extra-details" />

          <Separator />

          <ShiftRoster :bookings="shiftBookings" :capacity="capacity" :loading="loadingBookings" />

          <!-- Extensibility shift: additional sections below the table -->
          <slot name="extra-sections" />
        </template>
      </ResponsiveDialogBody>

      <ResponsiveDialogFooter v-if="resolvedShift" data-testid="shift-detail-footer" layout="row">
        <DropdownMenu v-if="hasMenuItems">
          <DropdownMenuTrigger as-child>
            <Button
              variant="outline"
              size="icon"
              class="size-10 md:size-9"
              :aria-label="t('common.actions.moreActions')"
            >
              <EllipsisVertical class="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuItem v-if="showTaskLink && resolvedShift?.task_id" @click="navigateToTask">
              <ExternalLink class="mr-2 h-4 w-4" />
              {{ t('duties.shifts.detail.viewTask') }}
            </DropdownMenuItem>
            <DropdownMenuItem v-if="resolvedMyBooking" @click="navigateToBooking">
              <ExternalLink class="mr-2 h-4 w-4" />
              {{ t('duties.shifts.detail.openBookingDetails') }}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <!--
          The action fills the row on a phone so it sits under the thumb, and
          keeps its natural width beside a spacer on a desktop dialog.
        -->
        <div class="hidden flex-1 md:block" />

        <p
          v-if="isShiftFull && !resolvedMyBooking"
          class="text-muted-foreground flex-1 text-sm md:flex-none"
        >
          {{ t('duties.shifts.detail.fullyBooked') }}
        </p>
        <p
          v-else-if="clashesWithMine"
          data-testid="shift-clash-note"
          class="text-destructive flex-1 text-sm md:flex-none"
        >
          {{ t('duties.shifts.detail.clashesWithMine') }}
        </p>
        <template v-else-if="lockedByTeam && resolvedShift?.team_id">
          <p
            data-testid="shift-team-note"
            class="text-muted-foreground flex min-w-0 flex-1 items-center gap-1.5 text-sm md:flex-none"
          >
            <Lock class="size-3.5 shrink-0" aria-hidden="true" />
            {{
              joinedStatus === 'pending' || resolvedShift.my_team_status === 'pending'
                ? t('teamLocks.join.pendingNamed', { name: resolvedShift.team_name })
                : t('teamLocks.gate.lockedShift', { name: resolvedShift.team_name })
            }}
          </p>
          <TeamJoinButton
            :event-id="resolvedShift.event_id"
            :team-id="resolvedShift.team_id"
            :team-name="resolvedShift.team_name ?? ''"
            :requires-approval="resolvedShift.team_requires_approval ?? true"
            :my-status="joinedStatus ?? resolvedShift.my_team_status"
            class="h-10 flex-1 md:h-9 md:flex-none"
            priority
            @joined="onTeamJoined"
          />
        </template>

        <Button
          v-if="canBook"
          data-testid="btn-book-shift"
          class="h-10 flex-1 md:h-9 md:flex-none"
          :disabled="bookingInProgress"
          @click="handleBook"
        >
          {{ t('duties.shifts.book') }}
        </Button>
        <Button
          v-if="resolvedMyBooking"
          data-testid="btn-cancel-shift-booking"
          variant="destructive"
          class="h-10 flex-1 md:h-9 md:flex-none"
          :disabled="bookingInProgress"
          @click="handleCancelBooking"
        >
          {{ t('duties.bookings.cancel') }}
        </Button>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
