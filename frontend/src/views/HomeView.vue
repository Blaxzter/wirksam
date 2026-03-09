<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { useLocalStorage } from '@vueuse/core'

import { BookCheck, CalendarDays, ClipboardList, SlidersHorizontal } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import type {
  BookingListResponse,
  DutySlotRead,
  EventGroupListResponse,
  EventGroupRead,
  EventListResponse,
  EventRead,
} from '@/client'
import { DutyCalendar } from '@/components/events/duty-calendar'
import type { BookingCalendarItem } from '@/components/events/duty-calendar'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import Label from '@/components/ui/label/Label.vue'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Switch } from '@/components/ui/switch'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { toastApiError } from '@/lib/api-errors'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const { get } = useAuthenticatedClient()

const eventCount = ref(0)
const myBookingCount = ref(0)
const loading = ref(true)

const events = ref<EventRead[]>([])
const eventGroups = ref<EventGroupRead[]>([])
const bookings = ref<BookingCalendarItem[]>([])

const showEvents = useLocalStorage('dutyhub-calendar-show-events', true)
const showGroups = useLocalStorage('dutyhub-calendar-show-groups', true)
const showBookings = useLocalStorage('dutyhub-calendar-show-bookings', true)

const hiddenFilterCount = computed(() =>
  [showEvents, showGroups, showBookings].filter((f) => !f.value).length,
)

async function loadStats() {
  loading.value = true
  try {
    const [eventsRes, groupsRes, bookingsRes] = await Promise.all([
      get<{ data: EventListResponse }>({ url: '/events/', query: { limit: 100 } }),
      get<{ data: EventGroupListResponse }>({ url: '/event-groups/', query: { limit: 100 } }),
      get<{ data: BookingListResponse }>({
        url: '/bookings/me',
        query: { status: 'confirmed', limit: 200 },
      }),
    ])
    events.value = eventsRes.data.items
    eventCount.value = eventsRes.data.total
    eventGroups.value = groupsRes.data.items
    myBookingCount.value = bookingsRes.data.total

    // Enrich bookings with slot details for calendar display
    const rawBookings = bookingsRes.data.items
    const settled = await Promise.all(
      rawBookings.map(async (booking): Promise<BookingCalendarItem | null> => {
        try {
          const slotRes = await get<{ data: DutySlotRead }>({
            url: `/duty-slots/${booking.duty_slot_id}`,
          })
          const slot = slotRes.data
          return {
            id: booking.id,
            date: slot.date,
            title: slot.title,
            startTime: slot.start_time,
            endTime: slot.end_time,
          }
        } catch {
          return null
        }
      }),
    )
    const enriched = settled.filter((b): b is BookingCalendarItem => b !== null)
    bookings.value = enriched
  } catch (error) {
    toastApiError(error)
  } finally {
    loading.value = false
  }
}

const navigateToEvent = (event: EventRead) => {
  router.push({ name: 'event-detail', params: { eventId: event.id } })
}

const navigateToGroup = (group: EventGroupRead) => {
  router.push({ name: 'event-group-detail', params: { groupId: group.id } })
}

const navigateToBookings = () => {
  router.push({ name: 'my-bookings' })
}

onMounted(loadStats)
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <div class="space-y-2">
      <h1 class="text-3xl font-bold">{{ t('dashboard.home.title') }}</h1>
      <p class="text-muted-foreground">
        {{ t('dashboard.home.subtitle') }}
      </p>
    </div>

    <!-- Stats Cards -->
    <div class="grid auto-rows-min gap-4 md:grid-cols-3">
      <Card
        class="cursor-pointer hover:shadow-md transition-shadow"
        @click="router.push({ name: 'events' })"
      >
        <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle class="text-sm font-medium">{{ t('dashboard.home.stats.events.title') }}</CardTitle>
          <CalendarDays class="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div class="text-2xl font-bold">{{ eventCount }}</div>
          <p class="text-xs text-muted-foreground">{{ t('dashboard.home.stats.events.description') }}</p>
        </CardContent>
      </Card>

      <Card
        class="cursor-pointer hover:shadow-md transition-shadow"
        @click="router.push({ name: 'my-bookings' })"
      >
        <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle class="text-sm font-medium">{{ t('dashboard.home.stats.bookings.title') }}</CardTitle>
          <BookCheck class="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div class="text-2xl font-bold">{{ myBookingCount }}</div>
          <p class="text-xs text-muted-foreground">{{ t('dashboard.home.stats.bookings.description') }}</p>
        </CardContent>
      </Card>

      <Card v-if="authStore.isAdmin">
        <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle class="text-sm font-medium">{{ t('dashboard.home.stats.admin.title') }}</CardTitle>
          <ClipboardList class="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <p class="text-xs text-muted-foreground">{{ t('dashboard.home.stats.admin.description') }}</p>
          <Button size="sm" class="mt-2" @click="router.push({ name: 'events' })">
            {{ t('dashboard.home.stats.admin.action') }}
          </Button>
        </CardContent>
      </Card>
    </div>

    <!-- Calendar Section -->
    <div class="space-y-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <h2 class="text-xl font-semibold">{{ t('dashboard.home.calendar.title') }}</h2>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger as="span" class="inline-flex">
              <Popover>
                <PopoverTrigger as-child>
                  <Button variant="outline" size="sm" class="relative">
                    <SlidersHorizontal class="mr-2 h-4 w-4" />
                    {{ t('dashboard.home.calendar.filter') }}
                    <span
                      v-if="hiddenFilterCount > 0"
                      class="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[10px] font-medium text-destructive-foreground"
                    >
                      {{ hiddenFilterCount }}
                    </span>
                  </Button>
                </PopoverTrigger>
                <PopoverContent align="end" class="w-56">
                  <div class="space-y-4">
                    <div class="flex items-center justify-between">
                      <Label for="filter-events">{{ t('dashboard.home.calendar.filters.events') }}</Label>
                      <Switch id="filter-events" v-model="showEvents" />
                    </div>
                    <div class="flex items-center justify-between">
                      <Label for="filter-groups">{{ t('dashboard.home.calendar.filters.groups') }}</Label>
                      <Switch id="filter-groups" v-model="showGroups" />
                    </div>
                    <div class="flex items-center justify-between">
                      <Label for="filter-bookings">{{ t('dashboard.home.calendar.filters.bookings') }}</Label>
                      <Switch id="filter-bookings" v-model="showBookings" />
                    </div>
                    <p v-if="hiddenFilterCount > 0" class="text-xs text-muted-foreground border-t pt-3">
                      {{ t('dashboard.home.calendar.hiddenCount', { count: hiddenFilterCount }, hiddenFilterCount) }}
                    </p>
                  </div>
                </PopoverContent>
              </Popover>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              <p v-if="hiddenFilterCount > 0">
                {{ t('dashboard.home.calendar.filterTooltip', { count: hiddenFilterCount }, hiddenFilterCount) }}
              </p>
              <p v-else>
                {{ t('dashboard.home.calendar.filterTooltipNone') }}
              </p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      <div v-if="loading" class="py-12 text-center text-muted-foreground">
        {{ t('common.states.loading') }}
      </div>
      <DutyCalendar
        v-else
        :events="events"
        :event-groups="eventGroups"
        :bookings="bookings"
        :show-events="showEvents"
        :show-groups="showGroups"
        :show-bookings="showBookings"
        @navigate-event="navigateToEvent"
        @navigate-group="navigateToGroup"
        @navigate-booking="navigateToBookings"
      />
    </div>

    <!-- Quick Actions -->
    <div class="rounded-xl bg-muted/50 p-6">
      <h2 class="text-xl font-semibold mb-4">{{ t('dashboard.home.quickActions.title') }}</h2>
      <div class="flex flex-wrap gap-3">
        <Button variant="outline" @click="router.push({ name: 'events' })">
          <CalendarDays class="mr-2 h-4 w-4" />
          {{ t('dashboard.home.quickActions.browseEvents') }}
        </Button>
        <Button variant="outline" @click="router.push({ name: 'my-bookings' })">
          <BookCheck class="mr-2 h-4 w-4" />
          {{ t('dashboard.home.quickActions.myBookings') }}
        </Button>
      </div>
    </div>
  </div>
</template>
