<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { Calendar, CalendarClock, CalendarSearch, Grid2x2, List, Plus, Search } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'
import { useTaskFiltersStore } from '@/stores/eventFilters'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Button from '@/components/ui/button/Button.vue'
import Input from '@/components/ui/input/Input.vue'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

import DeleteConfirmationDialog from '@/components/tasks/DeleteConfirmationDialog.vue'
import ShiftDetailDialog from '@/components/tasks/ShiftDetailDialog.vue'
import TaskCalendarView from '@/components/tasks/TaskCalendarView.vue'
import TaskFilterMenu from '@/components/tasks/TaskFilterMenu.vue'
import TaskListView from '@/components/tasks/TaskListView.vue'
import { TaskQuickView } from '@/components/tasks/quick-view'
import type { DateRange } from '@/components/tasks/shift-calendar'

import type { EventRead, FeedTaskItem, TaskFeedResponse } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const filters = useTaskFiltersStore()
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
  if (q.hide_full !== undefined) filters.hideFullShifts = q.hide_full === 'true'
  if (q.bookable !== undefined) filters.bookableOnly = q.bookable === 'true'
  if (q.date_from && /^\d{4}-\d{2}-\d{2}$/.test(String(q.date_from)))
    filters.dateFrom = String(q.date_from)
  if (q.date_to && /^\d{4}-\d{2}-\d{2}$/.test(String(q.date_to))) filters.dateTo = String(q.date_to)
  if (q.location && typeof q.location === 'string') filters.locationId = q.location
  if (q.cal_view && CAL_VIEW_MODES.includes(q.cal_view as CalViewMode))
    calViewMode.value = q.cal_view as CalViewMode
  if (q.cal_date && /^\d{4}-\d{2}-\d{2}$/.test(String(q.cal_date)))
    calDate.value = String(q.cal_date)
}
readUrlIntoStore()

// A location filter only makes sense within one event; switching drops it.
watch(
  () => authStore.selectedEventId,
  (id) => filters.setLocationEvent(id),
  { immediate: true },
)

// Mirror store → URL (replace, not push, to avoid polluting history)
const urlQuery = computed(() => {
  const q: Record<string, string> = {}
  if (filters.viewMode !== 'list') q.view = filters.viewMode
  if (filters.focusMode !== 'today') q.focus = filters.focusMode
  if (filters.searchQuery.trim()) q.search = filters.searchQuery.trim()
  if (filters.myBookingsOnly) q.my_bookings = 'true'
  if (filters.hideFullShifts) q.hide_full = 'true'
  if (filters.bookableOnly) q.bookable = 'true'
  if (filters.dateFrom) q.date_from = filters.dateFrom
  if (filters.dateTo) q.date_to = filters.dateTo
  if (filters.locationId) q.location = filters.locationId
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

const feedItems = ref<FeedTaskItem[]>([])
const events = ref<EventRead[]>([])
const loading = ref(false)
const calendarRange = ref<DateRange | null>(null)

// Shift detail dialog state
const showShiftDialog = ref(false)
const selectedShiftId = ref<string | null>(null)
const selectedShiftTaskName = ref<string | null>(null)

// Delete dialog state
const showDeleteDialog = ref(false)
const deleteReason = ref('')
const deleteTarget = ref<FeedTaskItem | null>(null)

// Map frontend view names to backend feed view param
function feedView(): 'list' | 'cards' | 'calendar' {
  if (filters.viewMode === 'box') return 'cards'
  return filters.viewMode
}

const loadTasks = async () => {
  loading.value = true
  try {
    const query: Record<string, unknown> = {
      view: feedView(),
      focus_mode: filters.focusMode === 'first-available' ? 'first_available' : 'today',
      limit: 100,
    }
    if (filters.myBookingsOnly) query.my_bookings = true
    if (filters.bookableOnly) query.bookable_only = true
    if (filters.dateFrom) query.date_from = filters.dateFrom
    if (filters.dateTo) query.date_to = filters.dateTo
    if (filters.searchQuery.trim()) query.search = filters.searchQuery.trim()
    if (filters.locationId) query.location_id = filters.locationId

    // Calendar view: scope to visible date range (overrides dateFrom)
    if (filters.viewMode === 'calendar' && calendarRange.value) {
      query.date_from = calendarRange.value.from
      query.date_to = calendarRange.value.to
    }

    const feedRes = await get<{ data: TaskFeedResponse }>({ url: '/tasks/feed', query })
    feedItems.value = feedRes.data.items
    events.value = authStore.selectedEvent ? [authStore.selectedEvent] : []
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
    searchTimer = setTimeout(() => loadTasks(), 300)
  },
)

// Re-fetch when these change
watch(
  () => [
    filters.myBookingsOnly,
    filters.bookableOnly,
    filters.viewMode,
    filters.focusMode,
    filters.dateFrom,
    filters.dateTo,
    filters.locationId,
  ],
  () => loadTasks(),
)

const handleDelete = (task: FeedTaskItem) => {
  deleteTarget.value = task
  deleteReason.value = ''
  showDeleteDialog.value = true
}

const confirmDeleteTask = async () => {
  if (!deleteTarget.value) return
  showDeleteDialog.value = false
  try {
    const query: Record<string, string> = {}
    if (deleteReason.value.trim()) query.cancellation_reason = deleteReason.value.trim()
    await del({ url: `/tasks/${deleteTarget.value.id}`, query })
    toast.success(t('duties.tasks.delete'))
    await loadTasks()
  } catch (error) {
    toastApiError(error)
  }
}

const handleClickShift = (slotId: string, task: FeedTaskItem) => {
  selectedShiftId.value = slotId
  selectedShiftTaskName.value = task.name
  showShiftDialog.value = true
}

const navigateToTask = (task: { id: string }) => {
  router.push({ name: 'task-detail', params: { eventId: task.id } })
}

const navigateToEvent = (event: { id: string }) => {
  if (authStore.canManageEvent(event.id)) {
    router.push({ name: 'event-settings', params: { eventId: event.id } })
  }
}

const handleCalendarDateRange = (range: DateRange) => {
  const changed = calendarRange.value?.from !== range.from || calendarRange.value?.to !== range.to
  calendarRange.value = range
  if (changed && filters.viewMode === 'calendar') loadTasks()
}

onMounted(loadTasks)
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <!-- Header -->
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div class="space-y-2">
        <h1 data-testid="page-heading" class="text-2xl sm:text-3xl font-bold">
          {{ t('duties.tasks.title') }}
        </h1>
        <p class="text-muted-foreground">{{ t('duties.tasks.subtitle') }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <!-- Focus Mode Toggle -->
        <TooltipProvider v-if="filters.viewMode === 'list'">
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            :model-value="filters.focusMode"
            @update:model-value="(v) => v && (filters.focusMode = v as typeof filters.focusMode)"
          >
            <Tooltip>
              <TooltipTrigger as-child>
                <ToggleGroupItem
                  value="today"
                  data-testid="btn-focus-today"
                  :aria-label="t('duties.tasks.focusMode.today')"
                >
                  <CalendarClock class="h-4 w-4" />
                </ToggleGroupItem>
              </TooltipTrigger>
              <TooltipContent>
                {{ t('duties.tasks.focusMode.today') }}
              </TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger as-child>
                <ToggleGroupItem
                  value="first-available"
                  data-testid="btn-focus-first-available"
                  :aria-label="t('duties.tasks.focusMode.firstAvailable')"
                >
                  <CalendarSearch class="h-4 w-4" />
                </ToggleGroupItem>
              </TooltipTrigger>
              <TooltipContent>
                {{ t('duties.tasks.focusMode.firstAvailable') }}
              </TooltipContent>
            </Tooltip>
          </ToggleGroup>
        </TooltipProvider>

        <!-- View Toggle -->
        <Tabs v-model="filters.viewMode">
          <TabsList>
            <TabsTrigger value="list" data-testid="btn-view-list">
              <List class="h-4 w-4" />
              <span class="hidden sm:inline">{{ t('duties.tasks.views.list') }}</span>
            </TabsTrigger>
            <TabsTrigger value="box" data-testid="btn-view-cards">
              <Grid2x2 class="h-4 w-4" />
              <span class="hidden sm:inline">{{ t('duties.tasks.views.box') }}</span>
            </TabsTrigger>
            <TabsTrigger value="calendar" data-testid="btn-view-calendar">
              <Calendar class="h-4 w-4" />
              <span class="hidden sm:inline">{{ t('duties.tasks.views.calendar') }}</span>
            </TabsTrigger>
          </TabsList>
        </Tabs>

        <Button
          v-if="authStore.isManager"
          data-testid="btn-create-task"
          class="max-xl:hidden"
          @click="router.push({ name: 'task-create' })"
        >
          <Plus class="mr-2 h-4 w-4" />
          {{ t('duties.tasks.create') }}
        </Button>
      </div>
    </div>

    <!-- Search & Filter (hidden for calendar — it has its own navigation) -->
    <div
      v-if="filters.viewMode !== 'calendar'"
      data-testid="task-board-filters"
      class="flex flex-wrap items-center gap-4"
    >
      <div class="relative flex-1">
        <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          v-model="filters.searchQuery"
          data-testid="input-search"
          :placeholder="t('common.actions.search')"
          class="pl-10"
        />
      </div>
      <TaskFilterMenu />
    </div>

    <!-- Loading (only shown on initial load, not calendar refetches) -->
    <div v-if="loading && feedItems.length === 0" class="py-12 text-center text-muted-foreground">
      {{ t('common.states.loading') }}
    </div>

    <template v-else>
      <TaskQuickView
        v-if="filters.viewMode === 'list'"
        :tasks="feedItems"
        :focus-mode="filters.focusMode"
        :hide-full-shifts="filters.hideFullShifts"
        @navigate="navigateToTask"
        @delete="handleDelete"
        @click-shift="handleClickShift"
        @team-joined="loadTasks"
      />
      <TaskListView
        v-else-if="filters.viewMode === 'box'"
        :tasks="feedItems"
        @navigate="navigateToTask"
        @delete="handleDelete"
        @team-joined="loadTasks"
      />
      <TaskCalendarView
        v-else
        :tasks="feedItems"
        :events="events"
        :calendar-view-mode="calViewMode"
        :calendar-date="calDate"
        @navigate="navigateToTask"
        @navigate-group="navigateToEvent"
        @update:date-range="handleCalendarDateRange"
        @update:calendar-view-mode="calViewMode = $event"
        @update:calendar-date="calDate = $event"
      />
    </template>

    <!-- Shift Detail Dialog -->
    <ShiftDetailDialog
      :shift-id="selectedShiftId"
      :task-name="selectedShiftTaskName"
      :open="showShiftDialog"
      @update:open="showShiftDialog = $event"
      @booking-updated="loadTasks"
      @team-joined="loadTasks"
    />

    <!-- Delete Task Dialog -->
    <DeleteConfirmationDialog
      v-model:open="showDeleteDialog"
      v-model:reason="deleteReason"
      :message="t('duties.tasks.deleteConfirm')"
      @confirm="confirmDeleteTask"
    />

    <!-- Mobile FAB: create task -->
    <Button
      v-if="authStore.isManager"
      size="icon"
      class="xl:hidden fixed bottom-24 md:bottom-6 right-6 z-40 h-14 w-14 rounded-full shadow-lg"
      data-testid="fab-create-task"
      :aria-label="t('duties.tasks.create')"
      @click="router.push({ name: 'task-create' })"
    >
      <Plus class="size-7" :stroke-width="2.5" />
    </Button>
  </div>
</template>
