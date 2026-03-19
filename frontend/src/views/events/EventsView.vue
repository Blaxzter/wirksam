<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import {
  Bookmark,
  Calendar,
  CalendarClock,
  CalendarSearch,
  EyeOff,
  Grid2x2,
  List,
  Plus,
  Search,
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import DeleteConfirmationDialog from '@/components/events/DeleteConfirmationDialog.vue'
import Button from '@/components/ui/button/Button.vue'
import Input from '@/components/ui/input/Input.vue'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'

import EventCalendarView from '@/components/events/EventCalendarView.vue'
import EventListView from '@/components/events/EventListView.vue'
import { EventQuickView } from '@/components/events/quick-view'
import SlotDetailDialog from '@/components/events/SlotDetailDialog.vue'

import type {
  EventFeedResponse,
  EventGroupListResponse,
  EventGroupRead,
  FeedEventItem,
} from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const { get, delete: del } = useAuthenticatedClient()

const feedItems = ref<FeedEventItem[]>([])
const eventGroups = ref<EventGroupRead[]>([])
const loading = ref(false)
const searchQuery = ref('')
const viewMode = ref<'list' | 'box' | 'calendar'>('list')
const focusMode = ref<'today' | 'first-available'>('today')
const myBookingsOnly = ref(false)
const hideFullSlots = ref(false)

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
  if (viewMode.value === 'box') return 'cards'
  return viewMode.value
}

const loadEvents = async () => {
  loading.value = true
  try {
    const query: Record<string, unknown> = {
      view: feedView(),
      focus_mode: focusMode.value === 'first-available' ? 'first_available' : 'today',
      limit: 100,
    }
    if (myBookingsOnly.value) query.my_bookings = true
    if (searchQuery.value.trim()) query.search = searchQuery.value.trim()

    const requests: Promise<unknown>[] = [
      get<{ data: EventFeedResponse }>({ url: '/events/feed', query }),
    ]
    // Event groups are only needed for calendar view
    if (viewMode.value === 'calendar') {
      requests.push(
        get<{ data: EventGroupListResponse }>({ url: '/event-groups/', query: { limit: 100 } }),
      )
    }

    const results = await Promise.all(requests)
    const feedRes = results[0] as { data: EventFeedResponse }
    feedItems.value = feedRes.data.items

    if (viewMode.value === 'calendar' && results[1]) {
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
watch(searchQuery, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => loadEvents(), 300)
})

// Re-fetch when these change
watch([myBookingsOnly, viewMode, focusMode], () => loadEvents())

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

onMounted(loadEvents)
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <!-- Header -->
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div class="space-y-2">
        <h1 class="text-3xl font-bold">{{ t('duties.events.title') }}</h1>
        <p class="text-muted-foreground">{{ t('duties.events.subtitle') }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <!-- Focus Mode Toggle -->
        <TooltipProvider v-if="viewMode === 'list'">
          <div class="flex overflow-hidden rounded-md border">
            <Tooltip>
              <TooltipTrigger as-child>
                <Button
                  :variant="focusMode === 'today' ? 'default' : 'ghost'"
                  size="sm"
                  class="rounded-none border-0"
                  @click="focusMode = 'today'"
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
                  :variant="focusMode === 'first-available' ? 'default' : 'ghost'"
                  size="sm"
                  class="rounded-none border-0 border-l"
                  @click="focusMode = 'first-available'"
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
            :variant="viewMode === 'list' ? 'default' : 'ghost'"
            size="sm"
            class="rounded-none border-0"
            @click="viewMode = 'list'"
          >
            <List class="mr-1.5 h-4 w-4" />
            <span class="hidden sm:inline">{{ t('duties.events.views.list') }}</span>
          </Button>
          <Button
            :variant="viewMode === 'box' ? 'default' : 'ghost'"
            size="sm"
            class="rounded-none border-0 border-l"
            @click="viewMode = 'box'"
          >
            <Grid2x2 class="mr-1.5 h-4 w-4" />
            <span class="hidden sm:inline">{{ t('duties.events.views.box') }}</span>
          </Button>
          <Button
            :variant="viewMode === 'calendar' ? 'default' : 'ghost'"
            size="sm"
            class="rounded-none border-0 border-l"
            @click="viewMode = 'calendar'"
          >
            <Calendar class="mr-1.5 h-4 w-4" />
            <span class="hidden sm:inline">{{ t('duties.events.views.calendar') }}</span>
          </Button>
        </div>

        <TooltipProvider v-if="authStore.isAdmin">
          <Tooltip>
            <TooltipTrigger as-child>
              <Button @click="router.push({ name: 'event-create' })">
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

    <!-- Search & Filter -->
    <div class="flex flex-wrap items-center gap-4">
      <div class="relative flex-1">
        <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input v-model="searchQuery" :placeholder="t('common.actions.search')" class="pl-10" />
      </div>
      <TooltipProvider>
        <div class="flex items-center gap-2">
          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                :variant="myBookingsOnly ? 'default' : 'outline'"
                size="sm"
                @click="myBookingsOnly = !myBookingsOnly"
              >
                <Bookmark class="h-4 w-4" />
                <span class="hidden sm:inline">{{ t('duties.events.myBookingsFilter') }}</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent class="sm:hidden">
              {{ t('duties.events.myBookingsFilter') }}
            </TooltipContent>
          </Tooltip>
          <Tooltip v-if="viewMode === 'list'">
            <TooltipTrigger as-child>
              <Button
                :variant="hideFullSlots ? 'default' : 'outline'"
                size="sm"
                @click="hideFullSlots = !hideFullSlots"
              >
                <EyeOff class="h-4 w-4" />
                <span class="hidden sm:inline">{{ t('duties.events.hideFullSlots') }}</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent class="sm:hidden">
              {{ t('duties.events.hideFullSlots') }}
            </TooltipContent>
          </Tooltip>
        </div>
      </TooltipProvider>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="py-12 text-center text-muted-foreground">
      {{ t('common.states.loading') }}
    </div>

    <template v-else>
      <EventQuickView
        v-if="viewMode === 'list'"
        :events="feedItems"
        :focus-mode="focusMode"
        :hide-full-slots="hideFullSlots"
        @navigate="navigateToEvent"
        @delete="handleDelete"
        @click-slot="handleClickSlot"
      />
      <EventListView
        v-else-if="viewMode === 'box'"
        :events="feedItems"
        @navigate="navigateToEvent"
        @delete="handleDelete"
      />
      <EventCalendarView
        v-else
        :events="feedItems"
        :event-groups="eventGroups"
        @navigate="navigateToEvent"
        @navigate-group="navigateToGroup"
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
