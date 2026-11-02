<script setup lang="ts">
/**
 * The dashboard.
 *
 * It used to be a month calendar with three date-range layers painted on it,
 * which looked like an overview and answered nothing: whether you are due
 * anywhere, and where people are still missing, both needed you to open the
 * grid and count. So the page became two lists and a headline — what you have
 * said yes to, and what still needs somebody — with the calendar left where it
 * belongs, on the Tasks screen, behind a view switch.
 *
 * The layout now leads with the next shift as a big green card: when, where,
 * how long until it starts, and on desktop a bar of the day. Beside it sits
 * what you have (your vouchers, and on a phone the hours you signed up for).
 * Below that comes what needs the organiser, then your whole plan day by day,
 * then the shifts still short of people as cards you can sign up from. Phones
 * read it top to bottom; on desktop the same DOM is laid out by grid, so
 * every test id exists exactly once at every width. The old "Anything else"
 * buttons went, because they repeated the navigation.
 *
 * The page keeps its own clock, ticking once a minute, which the countdown,
 * the greeting and every "today" label read, so they stay true while the tab
 * is left open, and a shift that ends while you look moves the card on.
 */
import { computed, onMounted, ref, watch } from 'vue'

import { useDocumentVisibility, useIntervalFn } from '@vueuse/core'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useMyVoucherAccount } from '@/composables/useMyVoucherAccount'

import AttentionList from '@/components/dashboard/AttentionList.vue'
import CommittedTile from '@/components/dashboard/CommittedTile.vue'
import DashboardHeader from '@/components/dashboard/DashboardHeader.vue'
import DashboardSkeleton from '@/components/dashboard/DashboardSkeleton.vue'
import DashboardVoucherCard from '@/components/dashboard/DashboardVoucherCard.vue'
import MyPlan from '@/components/dashboard/MyPlan.vue'
import NextShiftHero from '@/components/dashboard/NextShiftHero.vue'
import OpenShiftsSection from '@/components/dashboard/OpenShiftsSection.vue'
import ShiftDetailDialog from '@/components/tasks/ShiftDetailDialog.vue'
import VoucherCodeDialog from '@/components/vouchers/VoucherCodeDialog.vue'

import type { DashboardFeedResponse, DashboardShift } from '@/client'
import { toastApiError } from '@/lib/api-errors'
import { attentionItems, eventDay, greetingName } from '@/lib/dashboard'
import { scrollToSection } from '@/lib/scroll-to-section'
import { shiftHasEnded } from '@/lib/shift-time'

const authStore = useAuthStore()
const { get } = useAuthenticatedClient()
const vouchers = useMyVoucherAccount()

const feed = ref<DashboardFeedResponse | null>(null)
const loading = ref(true)
/** Bumped per request, so an answer for an event no longer selected is dropped. */
let feedRequest = 0

// The clock the countdown, greeting and "today" labels read. Refreshed every
// minute and whenever the tab comes back.
const now = ref(new Date())
useIntervalFn(() => {
  now.value = new Date()
}, 60_000)
watch(useDocumentVisibility(), (visibility) => {
  if (visibility === 'visible') now.value = new Date()
})

const detailShiftId = ref<string | null>(null)
const showShiftDetail = ref(false)
const codeOpen = ref(false)

const myShifts = computed<DashboardShift[]>(() => feed.value?.my_shifts ?? [])
const nextShift = computed<DashboardShift | null>(() => myShifts.value[0] ?? null)
const hasShift = computed(() => nextShift.value !== null)
const attention = computed(() => attentionItems(feed.value?.attention))
const showVouchers = computed(() => vouchers.visible.value && !!vouchers.account.value)
/** Wait for the voucher account too, so its card does not pop in after the rest. */
const ready = computed(() => !loading.value && vouchers.settled.value)

const greetName = computed(() => greetingName(authStore.profile))
const dayOfEvent = computed(() => eventDay(authStore.selectedEvent, now.value))
const venueMapEventId = computed(() => {
  const event = authStore.selectedEvent
  return event && (event.venue_plan_count ?? 0) > 0 ? event.id : null
})
const showHeaderFindShift = computed(() => !authStore.selectedEvent?.is_expired)

/**
 * The feed only sends shifts that have not started, so a running shift stays
 * on the card ("happening now") until it ends, and then the feed is re-read
 * and the next one moves up.
 */
const nextShiftOver = computed(
  () =>
    !!nextShift.value &&
    shiftHasEnded(
      nextShift.value.date,
      nextShift.value.start_time,
      nextShift.value.end_time,
      now.value,
    ),
)

async function loadFeed({ silent = false }: { silent?: boolean } = {}) {
  const id = ++feedRequest
  if (!silent) loading.value = true
  try {
    const res = await get<{ data: DashboardFeedResponse }>({ url: '/dashboard/feed' })
    if (id !== feedRequest) return
    feed.value = res.data
    // Join requests waiting on this user, across every event they run.
    authStore.notifyPendingJoinRequests(res.data.pending_join_request_count ?? 0)
    // The feed counts team requests across every event; the Teams badge
    // shows the selected event's share. Re-read that whenever either side
    // has any, so the badge follows the dashboard (none anywhere: nothing
    // can be stale).
    const selected = authStore.selectedEvent
    if (
      selected &&
      ((res.data.pending_team_request_count ?? 0) > 0 ||
        (selected.pending_team_request_count ?? 0) > 0)
    ) {
      void authStore.refreshSelectedEvent(selected.id)
    }
  } catch (error) {
    if (id === feedRequest) toastApiError(error)
  } finally {
    if (id === feedRequest) loading.value = false
  }
}

const openShiftDetail = (shiftId: string) => {
  detailShiftId.value = shiftId
  showShiftDetail.value = true
}

/** A booking or a team changed: the lists and the voucher balance may have too. */
function onBookingChanged() {
  void loadFeed({ silent: true })
  void vouchers.reload()
}

/**
 * The phone's "See my plan" button. A scroll rather than a `#dashboard-plan`
 * link, because the router-view key is the full path and a hash navigation
 * would remount the page. Focus follows, so a keyboard or screen reader user
 * lands where the screen went.
 */
function goToPlan() {
  if (scrollToSection('dashboard-plan')) {
    document.getElementById('dashboard-plan-title')?.focus({ preventScroll: true })
  }
}

onMounted(() => void loadFeed())

// Switching event from the header used to leave the old event's open shifts on
// screen until the next visit.
watch(
  () => authStore.selectedEventId,
  (next, prev) => {
    if (next !== prev) void loadFeed()
  },
)

watch(nextShiftOver, (over) => {
  if (over) void loadFeed({ silent: true })
})
</script>

<template>
  <div class="mx-auto max-w-[70rem] space-y-5 pt-4 pb-7 lg:space-y-6 lg:px-6 lg:pt-6 lg:pb-12">
    <DashboardHeader
      :now="now"
      :name="greetName"
      :event-day="dayOfEvent"
      :show-find-shift="showHeaderFindShift"
    />

    <DashboardSkeleton v-if="!ready" />

    <template v-else>
      <!-- Row 1: the next shift, and beside it what you have -->
      <div class="grid grid-cols-2 gap-x-3 gap-y-5 lg:grid-cols-3 lg:gap-6">
        <NextShiftHero
          class="col-span-2"
          :class="showVouchers ? 'lg:col-span-2' : 'lg:col-span-3'"
          :shift="nextShift"
          :now="now"
          :open-places="feed?.open_places ?? 0"
          :venue-map-event-id="venueMapEventId"
          :current-event-id="feed?.event_id ?? null"
          @open="openShiftDetail($event.shift_id)"
        />
        <DashboardVoucherCard
          v-if="showVouchers && vouchers.account.value && vouchers.eventId.value"
          :class="hasShift ? 'col-span-1' : 'col-span-2 lg:col-span-1'"
          :account="vouchers.account.value"
          :now="now"
          :event-id="vouchers.eventId.value"
          :expired="vouchers.isExpired.value"
          :can-show-code="vouchers.canShowCode.value"
          @show-code="codeOpen = true"
        />
        <CommittedTile
          v-if="hasShift"
          :class="showVouchers ? 'col-span-1' : 'col-span-2'"
          :minutes="feed?.my_minutes ?? 0"
          :shift-count="feed?.my_shift_count ?? 0"
          @to-plan="goToPlan"
        />
      </div>

      <!-- Row 2: what needs the organiser, and your plan -->
      <div
        v-if="attention.length > 0 || hasShift"
        class="grid gap-5 lg:grid-cols-3 lg:items-start lg:gap-6"
      >
        <AttentionList
          v-if="attention.length > 0"
          :items="attention"
          :event-id="feed?.event_id ?? null"
          :class="hasShift ? 'lg:col-start-3 lg:row-start-1' : 'lg:col-span-3'"
        />
        <MyPlan
          v-if="hasShift"
          :shifts="myShifts"
          :total-count="feed?.my_shift_count ?? 0"
          :minutes="feed?.my_minutes ?? 0"
          :current-event-id="feed?.event_id ?? null"
          :now="now"
          :class="
            attention.length > 0 ? 'lg:col-span-2 lg:col-start-1 lg:row-start-1' : 'lg:col-span-3'
          "
          @select="openShiftDetail"
        />
      </div>

      <OpenShiftsSection
        :shifts="feed?.open_shifts ?? []"
        :total-count="feed?.open_shift_count ?? 0"
        :open-places="feed?.open_places ?? 0"
        :now="now"
        :show-event-name="!feed?.event_id"
        @select="openShiftDetail"
      />
    </template>

    <ShiftDetailDialog
      v-model:open="showShiftDetail"
      :shift-id="detailShiftId"
      @booking-updated="onBookingChanged"
      @team-joined="onBookingChanged"
    />
    <VoucherCodeDialog
      v-if="vouchers.eventId.value"
      v-model:open="codeOpen"
      :event-id="vouchers.eventId.value"
      @redeemed="vouchers.reload"
    />
  </div>
</template>
