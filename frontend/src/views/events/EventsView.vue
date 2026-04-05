<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import {
  Calendar,
  CalendarClock,
  CalendarSearch,
  Grid2x2,
  List,
  Plus,
  Search,
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'
import { useEventFiltersStore } from '@/stores/eventFilters'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Button from '@/components/ui/button/Button.vue'
import Input from '@/components/ui/input/Input.vue'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

import DeleteConfirmationDialog from '@/components/events/DeleteConfirmationDialog.vue'
import EventCalendarView from '@/components/events/EventCalendarView.vue'
import EventFilterMenu from '@/components/events/EventFilterMenu.vue'
import EventListView from '@/components/events/EventListView.vue'
import SlotDetailDialog from '@/components/events/SlotDetailDialog.vue'
import type { DateRange } from '@/components/events/duty-calendar'
import { EventQuickView } from '@/components/events/quick-view'

import type {
  EventFeedResponse,
  EventGroupListResponse,
  EventGroupRead,
  FeedEventItem,
} from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const filters = useEventFiltersStore()
const { get, delete: del } = useAuthenticatedClient()

// ── URL ↔ filter sync ──

const VIEW_MODES = ['list', 'box', 'calendar'] as const
const FOCUS_MODES = ['today', 'first-available'] as const
const CAL_VIEW_MODES = ['month', 'week', 'day'] as const
type CalViewMode = (typeof CAL_VIEW_MODES)[number]

// Calendar internal state (synced to URL)
const calViewMode = ref<CalViewMode | undefined>(undefined)
const calDate = ref<string | undefined>(undefined)

// On mount: seed store from URL query params (URL wins over localStorage)
function readUrlIntoStore() {
  const q = route.query
  if (q.view && VIEW_MODES.includes(q.view as (typeof VIEW_MODES)[number]))
    filters.viewMode = q.view as (typeof VIEW_MODES)[number]
  if (q.focus && FOCUS_MODES.includes(q.focus as (typeof FOCUS_MODES)[number]))
    filters.focusMode = q.focus as (typeof FOCUS_MODES)[number]
  if (q.search !== undefined) filters.searchQuery = String(q.search)
  if (q.my_bookings !== undefined) filters.myBookingsOnly = q.my_bookings === 'true'
  if (q.hide_full !== undefined) filters.hideFullSlots = q.hide_full === 'true'
  if (q.date_from && /^\d{4}-\d{2}-\d{2}$/.test(String(q.date_from)))
    filters.dateFrom = String(q.date_from)
  if (q.date_to && /^\d{4}-\d{2}-\d{2}$/.test(String(q.date_to))) filters.dateTo = String(q.date_to)
  if (q.cal_view && CAL_VIEW_MODES.includes(q.cal_view as CalViewMode))
    calViewMode.value = q.cal_view as CalViewMode
  if (q.cal_date && /^\d{4}-\d{2}-\d{2}$/.test(String(q.cal_date)))
    calDate.value = String(q.cal_date)
}
readUrlIntoStore()

// Mirror store → URL (replace, not push, to avoid polluting history)
const urlQuery = computed(() => {
  const q: Record<string, string> = {}
  if (filters.viewMode !== 'list') q.view = filters.viewMode
  if (filters.focusMode !== 'today') q.focus = filters.focusMode
  if (filters.searchQuery.trim()) q.search = filters.searchQuery.trim()
  if (filters.myBookingsOnly) q.my_bookings = 'true'
  if (filters.hideFullSlots) q.hide_full = 'true'
  if (filters.dateFrom) q.date_from = filters.dateFrom
  if (filters.dateTo) q.date_to = filters.dateTo
  // Calendar-specific params (only when in calendar view)
  if (filters.viewMode === 'calendar') {
    if (calViewMode.value && calViewMode.value !== 'month') q.cal_view = calViewMode.value
    if (calDate.value) q.cal_date = calDate.value
  }
  return q
})

watch(urlQuery, (q) => {
  router.replace({ query: q })
})

// ── Data ──

const feedItems = ref<FeedEventItem[]>([])
const eventGroups = ref<EventGroupRead[]>([])
const loading = ref(false)
const calendarRange = ref<DateRange | null>(null)

// Slot detail dialog state
const showSlotDialog = ref(false)
const selectedSlotId = ref<string | null>(null)
const selectedSlotEventName = ref<string | null>(null)

// Delete dialog state
const showDeleteDialog = ref(false)
const deleteReason = ref('')
const deleteTarget = ref<FeedEventItem | null>(null)

// Map frontend view names to backend feed view param
function feedView(): 'list' | 'cards' | 'calendar' {
  if (filters.viewMode === 'box') return 'cards'
  return filters.viewMode
}

const loadEvents = async () => {
  loading.value = true
  try {
    const query: Record<string, unknown> = {
      view: feedView(),
      focus_mode: filters.focusMode === 'first-available' ? 'first_available' : 'today',
      limit: 100,
    }
    if (filters.myBookingsOnly) query.my_bookings = true
    if (filters.dateFrom) query.date_from = filters.dateFrom
    if (filters.dateTo) query.date_to = filters.dateTo
    if (filters.searchQuery.trim()) query.search = filters.searchQuery.trim()

    // Calendar view: scope to visible date range (overrides dateFrom)
    if (filters.viewMode === 'calendar' && calendarRange.value) {
      query.date_from = calendarRange.value.from
      query.date_to = calendarRange.value.to
    }

    const requests: Promise<unknown>[] = [
      get<{ data: EventFeedResponse }>({ url: '/events/feed', query }),
    ]
    // Event groups are only needed for calendar view
    if (filters.viewMode === 'calendar') {
      const groupQuery: Record<string, unknown> = { limit: 100 }
      if (calendarRange.value) {
        groupQuery.date_from = calendarRange.value.from
        groupQuery.date_to = calendarRange.value.to
      }
      requests.push(
        get<{ data: EventGroupListResponse }>({ url: '/event-groups/', query: groupQuery }),
      )
    }

    const results = await Promise.all(requests)
    const feedRes = results[0] as { data: EventFeedResponse }
    feedItems.value = feedRes.data.items

    if (filters.viewMode === 'calendar' && results[1]) {
      const groupsRes = results[1] as { data: EventGroupListResponse }
      eventGroups.value = groupsRes.data.items
    }
  } catch (error) {
    toastApiError(error)
  } finally {
    loading.value = false
  }
}

// Debounced search
let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(
  () => filters.searchQuery,
  () => {
    if (searchTimer) clearTimeout(searchTimer)
    searchTimer = setTimeout(() => loadEvents(), 300)
  },
)

// Re-fetch when these change
watch(
  () => [
    filters.myBookingsOnly,
    filters.viewMode,
    filters.focusMode,
    filters.dateFrom,
    filters.dateTo,
  ],
  () => loadEvents(),
)

const handleDelete = (event: FeedEventItem) => {
  deleteTarget.value = event
  deleteReason.value = ''
  showDeleteDialog.value = true
}

const confirmDeleteEvent = async () => {
  if (!deleteTarget.value) return
  showDeleteDialog.value = false
  try {
    const query: Record<string, string> = {}
    if (deleteReason.value.trim()) query.cancellation_reason = deleteReason.value.trim()
    await del({ url: `/events/${deleteTarget.value.id}`, query })
    toast.success(t('duties.events.delete'))
    await loadEvents()
  } catch (error) {
    toastApiError(error)
  }
}

const handleClickSlot = (slotId: string, event: FeedEventItem) => {
  selectedSlotId.value = slotId
  selectedSlotEventName.value = event.name
  showSlotDialog.value = true
}

const navigateToEvent = (event: { id: string }) => {
  router.push({ name: 'event-detail', params: { eventId: event.id } })
}

const navigateToGroup = (group: { id: string }) => {
  router.push({ name: 'event-group-detail', params: { groupId: group.id } })
}

const handleCalendarDateRange = (range: DateRange) => {
  const changed = calendarRange.value?.from !== range.from || calendarRange.value?.to !== range.to
  calendarRange.value = range
  if (changed && filters.viewMode === 'calendar') loadEvents()
}

onMounted(loadEvents)
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <!-- Header -->
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div class="space-y-2">
        <h1 data-testid="page-heading" class="text-3xl font-bold">{{ t('duties.events.title') }}</h1>
        <p class="text-muted-foreground">{{ t('duties.events.subtitle') }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <!-- Focus Mode Toggle -->
        <TooltipProvider v-if="filters.viewMode === 'list'">
          <div class="flex overflow-hidden rounded-md border">
            <Tooltip>
              <TooltipTrigger as-child>
                <Button
                  data-testid="btn-focus-today"
                  :variant="filters.focusMode === 'today' ? 'default' : 'ghost'"
                  size="sm"
                  class="rounded-none border-0"
                  @click="filters.focusMode = 'today'"
                >
                  <CalendarClock class="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                {{ t('duties.events.focusMode.today') }}
              </TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger as-child>
                <Button
                  data-testid="btn-focus-first-available"
                  :variant="filters.focusMode === 'first-available' ? 'default' : 'ghost'"
                  size="sm"
                  class="rounded-none border-0 border-l"
                  @click="filters.focusMode = 'first-available'"
                >
                  <CalendarSearch class="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                {{ t('duties.events.focusMode.firstAvailable') }}
              </TooltipContent>
            </Tooltip>
          </div>
        </TooltipProvider>

        <!-- View Toggle -->
        <div class="flex overflow-hidden rounded-md border">
          <Button
            data-testid="btn-view-list"
            :variant="filters.viewMode === 'list' ? 'default' : 'ghost'"
            size="sm"
            class="rounded-none border-0"
            @click="filters.viewMode = 'list'"
          >
            <List class="mr-1.5 h-4 w-4" />
            <span class="hidden sm:inline">{{ t('duties.events.views.list') }}</span>
          </Button>
          <Button
            data-testid="btn-view-cards"
            :variant="filters.viewMode === 'box' ? 'default' : 'ghost'"
            size="sm"
            class="rounded-none border-0 border-l"
            @click="filters.viewMode = 'box'"
          >
            <Grid2x2 class="mr-1.5 h-4 w-4" />
            <span class="hidden sm:inline">{{ t('duties.events.views.box') }}</span>
          </Button>
          <Button
            data-testid="btn-view-calendar"
            :variant="filters.viewMode === 'calendar' ? 'default' : 'ghost'"
            size="sm"
            class="rounded-none border-0 border-l"
            @click="filters.viewMode = 'calendar'"
          >
            <Calendar class="mr-1.5 h-4 w-4" />
            <span class="hidden sm:inline">{{ t('duties.events.views.calendar') }}</span>
          </Button>
        </div>

        <TooltipProvider v-if="authStore.isAdmin">
          <Tooltip>
            <TooltipTrigger as-child>
              <Button data-testid="btn-create-event" @click="router.push({ name: 'event-create' })">
                <Plus class="h-4 w-4" />
                <span class="hidden sm:inline">{{ t('duties.events.create') }}</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent class="sm:hidden">
              {{ t('duties.events.create') }}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    </div>

    <!-- Search & Filter (hidden for calendar — it has its own navigation) -->
    <div v-if="filters.viewMode !== 'calendar'" class="flex flex-wrap items-center gap-4">
      <div class="relative flex-1">
        <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          v-model="filters.searchQuery"
          data-testid="input-search"
          :placeholder="t('common.actions.search')"
          class="pl-10"
        />
      </div>
      <EventFilterMenu />
    </div>

    <!-- Loading (only shown on initial load, not calendar refetches) -->
    <div v-if="loading && feedItems.length === 0" class="py-12 text-center text-muted-foreground">
      {{ t('common.states.loading') }}
    </div>

    <template v-else>
      <EventQuickView
        v-if="filters.viewMode === 'list'"
        :events="feedItems"
        :focus-mode="filters.focusMode"
        :hide-full-slots="filters.hideFullSlots"
        @navigate="navigateToEvent"
        @delete="handleDelete"
        @click-slot="handleClickSlot"
      />
      <EventListView
        v-else-if="filters.viewMode === 'box'"
        :events="feedItems"
        @navigate="navigateToEvent"
        @delete="handleDelete"
      />
      <EventCalendarView
        v-else
        :events="feedItems"
        :event-groups="eventGroups"
        :calendar-view-mode="calViewMode"
        :calendar-date="calDate"
        @navigate="navigateToEvent"
        @navigate-group="navigateToGroup"
        @update:date-range="handleCalendarDateRange"
        @update:calendar-view-mode="calViewMode = $event"
        @update:calendar-date="calDate = $event"
      />
    </template>

    <!-- Slot Detail Dialog -->
    <SlotDetailDialog
      :slot-id="selectedSlotId"
      :event-name="selectedSlotEventName"
      :open="showSlotDialog"
      @update:open="showSlotDialog = $event"
      @booking-updated="loadEvents"
    />

    <!-- Delete Event Dialog -->
    <DeleteConfirmationDialog
      v-model:open="showDeleteDialog"
      v-model:reason="deleteReason"
      :message="t('duties.events.deleteConfirm')"
      @confirm="confirmDeleteEvent"
    />
  </div>
</template>
