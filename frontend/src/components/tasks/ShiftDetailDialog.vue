<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import {
  ChevronDown,
  EllipsisVertical,
  ExternalLink,
  Lock,
  Map as MapIcon,
  MapPin,
  Tag,
  Ticket,
} from '@lucide/vue'
import { useMediaQuery } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { avatarUrlFor } from '@/composables/useAvatarUrl'
import { useDialog } from '@/composables/useDialog'
import { useFormatters } from '@/composables/useFormatters'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import Button from '@/components/ui/button/Button.vue'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  RESPONSIVE_DIALOG_MOBILE_QUERY,
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogClose,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'

import { joinNames } from '@/components/events/teams/teamHelpers'
import LocationDescription from '@/components/locations/LocationDescription.vue'
import ShiftRoster from '@/components/tasks/ShiftRoster.vue'
import TeamJoinButton from '@/components/tasks/TeamJoinButton.vue'
import VenueMiniMap from '@/components/venue-map/VenueMiniMap.vue'

import type {
  BookingRead,
  LocationDetailRead,
  ShiftBookingEntry,
  ShiftRead,
  TaskManagerBrief,
  TaskRead,
} from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { initials } from '@/lib/format'
import { shiftHasEnded, shiftHasStarted } from '@/lib/shift-time'

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
    /**
     * The task's vouchers per shift. Such a shift can only be booked before it
     * starts (`booking.shift_started`), unless the viewer can manage the task.
     * Unknown (omitted) means the server alone decides.
     */
    vouchersPerShift?: number | null
    /** The viewer is an organiser or in charge of the task. */
    canManageTask?: boolean
    /**
     * Who is in charge of the task. Omitted, the dialog reads the task itself,
     * which also fills in its vouchers and whether the viewer runs it.
     */
    managers?: TaskManagerBrief[]
    open: boolean
  }>(),
  {
    showTaskLink: true,
    priority: false,
    vouchersPerShift: null,
    canManageTask: false,
    managers: undefined,
  },
)

const emit = defineEmits<{
  'update:open': [value: boolean]
  'booking-updated': []
  /** The user joined (or asked to join) the team the shift is reserved for. */
  'team-joined': [status: 'approved' | 'pending']
}>()

const { t, locale } = useI18n()
const { formatTimeRange, formatDateLabel } = useFormatters()
const isPhone = useMediaQuery(RESPONSIVE_DIALOG_MOBILE_QUERY)
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
// "Location and site plan", below the roster: how to get there, who to ask and
// where on the map. Descriptions up to this length start expanded; a longer
// one starts folded, so the plan under it stays in reach.
const SHORT_DESCRIPTION = 280

const locationDetail = ref<LocationDetailRead | null>(null)
const locationDetailsOpen = ref(false)

const locationHasDetails = computed(() => {
  const l = locationDetail.value
  return !!(l && (l.description?.trim() || l.address || l.map_url || l.contact))
})
const locationPin = computed(() => locationDetail.value?.pins?.[0] ?? null)
const showLocation = computed(() => locationHasDetails.value || !!locationPin.value)

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

// --- The task behind it ---
// Callers on the task page and the task list hand over the people in charge;
// the dashboard and the map only know the shift, so the dialog reads the task
// for them. Failing that (an archived task a booker reopens, say) costs only
// the "In charge" line.
const fetchedTask = ref<TaskRead | null>(null)

watch(
  () =>
    props.open && props.managers === undefined ? (resolvedShift.value?.task_id ?? null) : null,
  async (taskId) => {
    if (!taskId) {
      fetchedTask.value = null
      return
    }
    if (fetchedTask.value?.id === taskId) return
    try {
      const res = await get<{ data: TaskRead }>({ url: `/tasks/${taskId}` })
      if ((resolvedShift.value?.task_id ?? null) !== taskId) return
      fetchedTask.value = res.data
    } catch {
      fetchedTask.value = null
    }
  },
  { immediate: true },
)

const taskManagers = computed(() => props.managers ?? fetchedTask.value?.managers ?? [])
const voucherCount = computed(
  () => props.vouchersPerShift ?? fetchedTask.value?.vouchers_per_shift ?? null,
)
const canManage = computed(() => props.canManageTask || !!fetchedTask.value?.can_manage)

const myId = computed(() => authStore.profile?.id ?? authStore.user?.id ?? null)

/** Others first, the viewer last: "Mira Lindqvist and you". */
const managersInOrder = computed(() => {
  const me = myId.value
  return [
    ...taskManagers.value.filter((m) => m.user_id !== me),
    ...taskManagers.value.filter((m) => m.user_id === me),
  ]
})

const managerNames = computed(() => {
  const me = myId.value
  const others = managersInOrder.value.filter((m) => m.user_id !== me).map((m) => m.name || '?')
  const mine = managersInOrder.value.length > others.length
  if (mine && others.length === 0) return t('duties.tasks.managers.you')
  return joinNames(mine ? [...others, t('duties.shifts.detail.youInList')] : others, locale.value)
})

/** Three faces at most, the viewer's among them; the names say the rest. */
const managerFaces = computed(() => {
  const all = managersInOrder.value
  if (all.length <= 3) return all
  const mine = all.filter((m) => m.user_id === myId.value)
  return [...all.filter((m) => m.user_id !== myId.value).slice(0, 3 - mine.length), ...mine]
})

const managerAvatar = (m: TaskManagerBrief) =>
  avatarUrlFor({ id: m.user_id, avatar_etag: m.avatar_etag ?? null })

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

/**
 * "Saturday, 18 July · 14:00 – 17:00" — the one line people actually scan for.
 * The year only when it isn't this one.
 */
const whenLine = computed(() => {
  const s = resolvedShift.value
  if (!s) return loadingShift.value ? t('common.states.loading') : (props.taskName ?? '')
  const options: Intl.DateTimeFormatOptions = { weekday: 'long', day: 'numeric', month: 'long' }
  if (Number(s.date.slice(0, 4)) !== new Date().getFullYear()) options.year = 'numeric'
  const date = formatDateLabel(s.date, options)
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

/** Over: nothing can be booked or cancelled any more (`booking.shift_over`). */
const hasEnded = computed(() => {
  const s = resolvedShift.value
  return !!s && shiftHasEnded(s.date, s.start_time, s.end_time)
})

/** A voucher shift that has begun, for someone who does not run the task. */
const startedForVouchers = computed(() => {
  const s = resolvedShift.value
  return (
    !!s &&
    (voucherCount.value ?? 0) > 0 &&
    !canManage.value &&
    shiftHasStarted(s.date, s.start_time)
  )
})

const canBook = computed(() => {
  return (
    !hasEnded.value &&
    !startedForVouchers.value &&
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

// --- Presentation ---
const chipClass =
  'flex min-h-[30px] max-w-full min-w-0 items-center gap-1.5 rounded-full bg-muted px-2.5 text-[13px] font-semibold'

const earns = computed(() => (voucherCount.value ?? 0) > 0)
const facts = computed(
  () =>
    !!resolvedShift.value?.location ||
    (!!resolvedShift.value?.category && !isPhone.value) ||
    earns.value,
)

/** A footer note fills the row on a phone and sits left of the buttons on a desktop. */
const noteClass = computed(() =>
  isPhone.value ? 'flex-1 text-sm text-muted-foreground' : 'text-sm text-muted-foreground',
)

/** Thumb-sized and full width on a phone; a 44px row on a desktop. */
const actionClass = computed(() =>
  isPhone.value
    ? 'h-[50px] flex-1 rounded-xl text-base font-bold'
    : 'h-11 rounded-xl px-[18px] font-bold',
)
</script>

<template>
  <ResponsiveDialog v-model:open="dialogOpen">
    <ResponsiveDialogContent
      data-testid="dialog-shift-detail"
      class="bg-card"
      dialog-class="rounded-[20px] sm:max-w-[620px]"
      drawer-class="rounded-t-[22px] data-[swipe-direction=down]:max-h-[calc(100dvh-2.25rem)]"
      :priority="priority"
    >
      <ResponsiveDialogHeader :class="isPhone ? 'gap-0.5 pt-2.5' : 'gap-1 pt-[26px] pb-5 pl-7'">
        <ResponsiveDialogTitle
          data-testid="shift-detail-title"
          class="text-[22px] leading-tight font-bold"
        >
          {{ headline }}
        </ResponsiveDialogTitle>
        <ResponsiveDialogDescription class="text-[15px] text-foreground/80 tabular-nums">
          {{ whenLine }}
        </ResponsiveDialogDescription>
      </ResponsiveDialogHeader>

      <ResponsiveDialogBody
        class="flex flex-col"
        :class="isPhone ? 'gap-[18px] pt-1 pb-4' : 'gap-5 px-7 pb-2'"
      >
        <p v-if="loadingShift" class="py-8 text-center text-sm text-muted-foreground">
          {{ t('common.states.loading') }}
        </p>

        <template v-else-if="resolvedShift">
          <!-- Where, what, and what it earns: a row of chips that wraps -->
          <ul v-if="facts" class="flex flex-wrap gap-1.5" data-testid="shift-detail-facts">
            <li v-if="resolvedShift.location" :class="chipClass">
              <MapPin class="size-3.5 shrink-0" aria-hidden="true" />
              <span class="truncate">{{ resolvedShift.location }}</span>
            </li>
            <!-- A phone keeps the chips to one row; the category is the one to go -->
            <li v-if="resolvedShift.category && !isPhone" :class="chipClass">
              <Tag class="size-3.5 shrink-0" aria-hidden="true" />
              <span class="truncate">{{ resolvedShift.category }}</span>
            </li>
            <li v-if="earns" :class="chipClass" data-testid="shift-detail-vouchers">
              <Ticket class="size-3.5 shrink-0" aria-hidden="true" />
              {{ t('vouchers.task.perPerson', { n: voucherCount }, voucherCount ?? 0) }}
            </li>
          </ul>

          <p v-if="resolvedShift.description" class="text-sm whitespace-pre-line">
            {{ resolvedShift.description }}
          </p>

          <!-- Who runs it: faces, then names, the viewer last as "you" -->
          <section
            v-if="managersInOrder.length > 0"
            aria-labelledby="shift-in-charge-title"
            class="flex items-center gap-3 rounded-[14px] bg-muted/60 px-3.5 py-3"
            data-testid="shift-in-charge"
          >
            <span class="flex shrink-0" aria-hidden="true">
              <Avatar
                v-for="(m, i) in managerFaces"
                :key="m.user_id"
                class="size-[34px] border-2 border-card"
                :class="i > 0 ? '-ml-2.5' : ''"
              >
                <AvatarImage v-if="managerAvatar(m)" :src="managerAvatar(m)!" alt="" />
                <AvatarFallback
                  class="text-xs font-bold"
                  :class="
                    m.user_id === myId
                      ? 'bg-primary/15 text-primary'
                      : 'bg-accent text-accent-foreground'
                  "
                >
                  {{ initials(m.name || '?') }}
                </AvatarFallback>
              </Avatar>
            </span>
            <div class="min-w-0 flex-1">
              <h3
                id="shift-in-charge-title"
                class="text-xs font-bold tracking-[0.05em] text-muted-foreground uppercase"
              >
                {{ t('duties.tasks.managers.label') }}
              </h3>
              <p class="text-[15px] font-semibold" data-testid="shift-in-charge-names">
                {{ managerNames }}
              </p>
            </div>
          </section>

          <ShiftRoster
            :bookings="shiftBookings"
            :capacity="capacity"
            :loading="loadingBookings"
            :booked="bookedCount"
            :hide-free="hasEnded"
            :compact="isPhone"
            :my-id="myId"
          />

          <!-- The place itself: how to get there, who to ask, where on the map -->
          <Collapsible
            v-if="locationDetail && showLocation"
            v-model:open="locationDetailsOpen"
            class="rounded-[14px] border bg-card"
            data-testid="shift-location-details"
          >
            <CollapsibleTrigger as-child>
              <button
                type="button"
                class="flex min-h-12 w-full items-center gap-2.5 rounded-[14px] px-3.5 text-left text-[15px] font-semibold outline-none hover:bg-muted/50 focus-visible:ring-[3px] focus-visible:ring-ring/50 md:min-h-[46px]"
              >
                <MapIcon class="size-[18px] shrink-0 text-muted-foreground" aria-hidden="true" />
                <span class="flex-1">
                  {{
                    locationPin
                      ? t('duties.shifts.detail.placeAndPlan')
                      : t('locations.details.title')
                  }}
                </span>
                <ChevronDown
                  class="size-4 shrink-0 text-muted-foreground transition-transform"
                  :class="{ 'rotate-180': locationDetailsOpen }"
                  aria-hidden="true"
                />
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div class="flex flex-col gap-3 px-3.5 pb-3.5">
                <LocationDescription v-if="locationHasDetails" :location="locationDetail" />
                <!-- Following the link leaves this dialog behind, so close it. -->
                <div v-if="locationPin" data-testid="shift-mini-map" @click="dialogOpen = false">
                  <VenueMiniMap
                    :event-id="locationDetail.event_id"
                    :pin="locationPin"
                    :location-id="locationDetail.id"
                  />
                </div>
              </div>
            </CollapsibleContent>
          </Collapsible>

          <!-- Extensibility shift: future fields (materials, protection, etc.) go here -->
          <slot name="extra-details" />

          <!-- Extensibility shift: additional sections below the table -->
          <slot name="extra-sections" />
        </template>
      </ResponsiveDialogBody>

      <ResponsiveDialogFooter
        v-if="resolvedShift"
        data-testid="shift-detail-footer"
        layout="row"
        :class="isPhone ? 'pb-[max(1.25rem,env(safe-area-inset-bottom))]' : 'px-7 pt-5 pb-6'"
      >
        <DropdownMenu v-if="hasMenuItems">
          <DropdownMenuTrigger as-child>
            <Button
              variant="outline"
              size="icon"
              :class="isPhone ? 'size-[50px] rounded-xl' : 'size-11 rounded-xl'"
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
          keeps its natural width at the right of a desktop dialog.
        -->
        <div v-if="!isPhone" class="flex-1" />

        <p v-if="hasEnded && !resolvedMyBooking" data-testid="shift-over-note" :class="noteClass">
          {{ t('duties.shifts.detail.over') }}
        </p>
        <p
          v-else-if="startedForVouchers && !resolvedMyBooking"
          data-testid="shift-started-note"
          :class="noteClass"
        >
          {{ t('vouchers.task.startedNote') }}
        </p>
        <p v-else-if="isShiftFull && !resolvedMyBooking" :class="noteClass">
          {{ t('duties.shifts.detail.fullyBooked') }}
        </p>
        <p
          v-else-if="clashesWithMine"
          data-testid="shift-clash-note"
          :class="[noteClass, 'text-destructive']"
        >
          {{ t('duties.shifts.detail.clashesWithMine') }}
        </p>
        <template v-else-if="lockedByTeam && resolvedShift?.team_id">
          <p
            data-testid="shift-team-note"
            :class="[noteClass, 'flex min-w-0 items-center gap-1.5']"
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
            :class="actionClass"
            priority
            @joined="onTeamJoined"
          />
        </template>

        <ResponsiveDialogClose v-if="!isPhone" as-child>
          <Button variant="outline" :class="[actionClass, 'font-semibold']">
            {{ t('common.actions.close') }}
          </Button>
        </ResponsiveDialogClose>

        <Button
          v-if="canBook"
          data-testid="btn-book-shift"
          :class="actionClass"
          :disabled="bookingInProgress"
          @click="handleBook"
        >
          {{ t('duties.shifts.detail.signMeUp') }}
        </Button>
        <Button
          v-if="resolvedMyBooking && !hasEnded"
          data-testid="btn-cancel-shift-booking"
          variant="destructive"
          :class="actionClass"
          :disabled="bookingInProgress"
          @click="handleCancelBooking"
        >
          {{ t('duties.bookings.cancel') }}
        </Button>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
