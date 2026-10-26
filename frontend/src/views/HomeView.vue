<script setup lang="ts">
/**
 * The dashboard.
 *
 * It used to be a month calendar with three date-range layers painted on it,
 * which looked like an overview and answered nothing: whether you are due
 * anywhere, and where people are still missing, both needed you to open the
 * grid and count. So the page is now two lists and a headline — what you have
 * said yes to, and what still needs somebody — with the calendar left where it
 * belongs, on the Tasks screen, behind a view switch.
 */
import { computed, onMounted, ref } from 'vue'

import { ArrowRight, BookCheck, HelpCircle, Search } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

import { isSwitchOn, useAppConfig } from '@/composables/useAppConfig'
import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

import AttentionStrip from '@/components/dashboard/AttentionStrip.vue'
import NextShiftCard from '@/components/dashboard/NextShiftCard.vue'
import ShiftRow from '@/components/dashboard/ShiftRow.vue'
import ShiftDetailDialog from '@/components/tasks/ShiftDetailDialog.vue'

import type { DashboardFeedResponse, DashboardOpenShift, DashboardShift } from '@/client'
import { toastApiError } from '@/lib/api-errors'

const { t, locale } = useI18n()
const router = useRouter()
const landingEnabled = isSwitchOn(useAppConfig().LANDING_ENABLED)
const authStore = useAuthStore()
const { get } = useAuthenticatedClient()

const feed = ref<DashboardFeedResponse | null>(null)
const loading = ref(true)

const detailShiftId = ref<string | null>(null)
const showShiftDetail = ref(false)

const todayStr = computed(() => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
})

const nextShift = computed<DashboardShift | null>(() => feed.value?.my_shifts[0] ?? null)
/** Everything after the headline one — the headline is not repeated below it. */
const laterShifts = computed<DashboardShift[]>(() => feed.value?.my_shifts.slice(1) ?? [])
const openShifts = computed<DashboardOpenShift[]>(() => feed.value?.open_shifts ?? [])

/** Rows the feed knows about but did not send, so the lists can say so. */
const hiddenMine = computed(() =>
  Math.max((feed.value?.my_shift_count ?? 0) - (feed.value?.my_shifts.length ?? 0), 0),
)
const hiddenOpen = computed(() =>
  Math.max((feed.value?.open_shift_count ?? 0) - openShifts.value.length, 0),
)

const committedHours = computed(() => {
  const hours = (feed.value?.my_minutes ?? 0) / 60
  return hours.toLocaleString(locale.value, { maximumFractionDigits: 1 })
})

/**
 * A shift in some other event than the one selected, labelled so. Your own
 * duties are listed across every event you belong to — a promise to turn up
 * should not vanish because the event switcher is pointing elsewhere — and
 * without the name that list would silently mix two schedules together.
 */
const foreignEventName = (shift: DashboardShift): string | null =>
  shift.event_id && shift.event_id !== feed.value?.event_id ? (shift.event_name ?? null) : null

async function loadFeed() {
  loading.value = true
  try {
    const res = await get<{ data: DashboardFeedResponse }>({ url: '/dashboard/feed' })
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
    toastApiError(error)
  } finally {
    loading.value = false
  }
}

const openShiftDetail = (shiftId: string) => {
  detailShiftId.value = shiftId
  showShiftDetail.value = true
}

const goBrowseOpenShifts = () => router.push({ name: 'tasks', query: { hide_full: 'true' } })

onMounted(loadFeed)
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <div class="space-y-2">
      <h1 data-testid="page-heading" class="text-2xl font-bold sm:text-3xl">
        {{ t('dashboard.home.title') }}
      </h1>
      <p class="text-muted-foreground">
        {{
          feed?.event_name
            ? t('dashboard.home.subtitleEvent', { event: feed.event_name })
            : t('dashboard.home.subtitle')
        }}
      </p>
    </div>

    <div v-if="loading" class="space-y-6">
      <Skeleton class="h-40 w-full rounded-xl" />
      <div class="grid gap-6 lg:grid-cols-2">
        <Skeleton class="h-64 w-full rounded-xl" />
        <Skeleton class="h-64 w-full rounded-xl" />
      </div>
    </div>

    <template v-else>
      <!-- Organisers only: the backend sends nothing here for a plain member. -->
      <AttentionStrip
        v-if="feed?.attention"
        :attention="feed.attention"
        :event-id="feed.event_id"
      />

      <NextShiftCard
        :shift="nextShift"
        :open-places="feed?.open_places ?? 0"
        @open="openShiftDetail($event.shift_id)"
        @browse="goBrowseOpenShifts"
      />

      <!--
        `items-start` so a short list does not stretch into a void beside a long
        one. `min-w-0` on each card because a grid item defaults to
        `min-width: auto` and will not shrink below its content — without it a
        long shift title pushes the whole card past the screen on a phone.
      -->
      <div class="grid items-start gap-6 lg:grid-cols-2">
        <!-- What else you have said yes to -->
        <Card v-if="laterShifts.length > 0" data-testid="dashboard-my-shifts" class="min-w-0">
          <CardHeader class="flex flex-row items-start justify-between gap-2 space-y-0">
            <div class="min-w-0">
              <CardTitle class="text-base">{{ t('dashboard.home.mine.title') }}</CardTitle>
              <p class="mt-1 text-sm text-muted-foreground">
                {{
                  t(
                    'dashboard.home.mine.summaryCount',
                    { count: feed?.my_shift_count ?? 0 },
                    feed?.my_shift_count ?? 0,
                  )
                }}<template v-if="(feed?.my_minutes ?? 0) > 0">
                  · {{ t('dashboard.home.mine.summaryHours', { hours: committedHours }) }}
                </template>
              </p>
            </div>
            <Button
              data-testid="btn-all-bookings"
              variant="ghost"
              size="sm"
              class="shrink-0"
              @click="router.push({ name: 'my-bookings' })"
            >
              {{ t('dashboard.home.mine.all') }}
              <ArrowRight class="ml-1 h-4 w-4" />
            </Button>
          </CardHeader>
          <CardContent class="space-y-1">
            <ShiftRow
              v-for="shift in laterShifts"
              :key="shift.booking_id"
              :date="shift.date"
              :start-time="shift.start_time"
              :end-time="shift.end_time"
              :title="shift.title"
              :task-name="shift.task_name"
              :location="shift.location"
              :event-name="foreignEventName(shift)"
              :highlight="shift.date === todayStr"
              @select="openShiftDetail(shift.shift_id)"
            />
            <p v-if="hiddenMine > 0" class="px-2 pt-1 text-xs text-muted-foreground">
              {{ t('dashboard.home.mine.more', { count: hiddenMine }, hiddenMine) }}
            </p>
          </CardContent>
        </Card>

        <!-- Where the event is still short of people -->
        <Card
          data-testid="dashboard-open-shifts"
          :class="['min-w-0', laterShifts.length > 0 ? '' : 'lg:col-span-2']"
        >
          <CardHeader class="flex flex-row items-start justify-between gap-2 space-y-0">
            <div class="min-w-0">
              <CardTitle class="text-base">{{ t('dashboard.home.open.title') }}</CardTitle>
              <p class="mt-1 text-sm text-muted-foreground">
                <template v-if="feed && feed.open_places > 0">
                  {{
                    t(
                      'dashboard.home.open.summaryPlaces',
                      { count: feed.open_places },
                      feed.open_places,
                    )
                  }}
                  {{
                    t(
                      'dashboard.home.open.summaryShifts',
                      { count: feed.open_shift_count },
                      feed.open_shift_count,
                    )
                  }}
                </template>
                <template v-else>{{ t('dashboard.home.open.emptySummary') }}</template>
              </p>
            </div>
            <Button
              data-testid="btn-browse-open-shifts"
              variant="ghost"
              size="sm"
              class="shrink-0"
              @click="goBrowseOpenShifts"
            >
              {{ t('dashboard.home.open.browse') }}
              <ArrowRight class="ml-1 h-4 w-4" />
            </Button>
          </CardHeader>
          <CardContent class="space-y-1">
            <ShiftRow
              v-for="shift in openShifts"
              :key="shift.shift_id"
              :date="shift.date"
              :start-time="shift.start_time"
              :end-time="shift.end_time"
              :title="shift.title"
              :task-name="shift.task_name"
              :location="shift.location"
              :highlight="shift.date === todayStr"
              @select="openShiftDetail(shift.shift_id)"
            >
              <template #trailing>
                <Badge :variant="shift.taken === 0 ? 'warning' : 'secondary'">
                  {{
                    shift.taken === 0
                      ? t('dashboard.home.open.nobodyYet')
                      : t(
                          'dashboard.home.open.placesLeft',
                          { count: shift.places_left },
                          shift.places_left,
                        )
                  }}
                </Badge>
              </template>
            </ShiftRow>

            <p v-if="hiddenOpen > 0" class="px-2 pt-1 text-xs text-muted-foreground">
              {{ t('dashboard.home.open.more', { count: hiddenOpen }, hiddenOpen) }}
            </p>

            <div
              v-if="openShifts.length === 0"
              class="flex flex-col items-center gap-1 py-8 text-center"
            >
              <p class="font-medium">{{ t('dashboard.home.open.emptyTitle') }}</p>
              <p class="text-sm text-muted-foreground">{{ t('dashboard.home.open.emptyBody') }}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <!-- Quick Actions -->
      <div data-testid="dashboard-quick-actions" class="rounded-xl bg-muted/50 p-6">
        <h2 class="mb-4 text-xl font-semibold">{{ t('dashboard.home.quickActions.title') }}</h2>
        <div class="flex flex-wrap gap-3">
          <Button
            data-testid="btn-browse-tasks"
            variant="outline"
            @click="router.push({ name: 'tasks' })"
          >
            <Search class="mr-2 h-4 w-4" />
            {{ t('dashboard.home.quickActions.browseTasks') }}
          </Button>
          <Button
            data-testid="btn-my-bookings"
            variant="outline"
            @click="router.push({ name: 'my-bookings' })"
          >
            <BookCheck class="mr-2 h-4 w-4" />
            {{ t('dashboard.home.quickActions.myBookings') }}
          </Button>
          <!-- The walkthrough lives on the landing page, which a deployment can switch off. -->
          <Button
            v-if="landingEnabled"
            variant="outline"
            @click="router.push({ name: 'landing', hash: '#how-it-works' })"
          >
            <HelpCircle class="mr-2 h-4 w-4" />
            {{ t('dashboard.home.quickActions.howItWorks') }}
          </Button>
        </div>
      </div>
    </template>

    <ShiftDetailDialog
      v-model:open="showShiftDetail"
      :shift-id="detailShiftId"
      @booking-updated="loadFeed"
      @team-joined="loadFeed"
    />
  </div>
</template>
