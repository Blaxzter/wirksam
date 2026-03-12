<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { Loader2 } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import type { DutySlotListResponse, DutySlotRead, EventRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

import EventQuickViewCard from './EventQuickViewCard.vue'

const PAGE_SIZE = 8

const props = defineProps<{
  events: EventRead[]
  focusMode?: 'today' | 'first-available'
  hideFullSlots?: boolean
}>()

const emit = defineEmits<{
  navigate: [event: EventRead]
  delete: [event: EventRead]
  clickSlot: [slotId: string, event: EventRead]
}>()

const { t } = useI18n()
const { get } = useAuthenticatedClient()

const slotsByEvent = ref<Map<string, DutySlotRead[]>>(new Map())
const loadedEventIds = ref<Set<string>>(new Set())
const visibleCount = ref(PAGE_SIZE)
const loadingSlots = ref(false)
const loadingMore = ref(false)
const sentinelRef = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

const today = computed(() => {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d
})

const todayStr = computed(() => {
  const d = today.value
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
})

/**
 * Pre-sort events by start_date proximity to today as initial approximation.
 * Once slots are loaded, re-sort by actual next available slot.
 */
const sortedEvents = computed(() => {
  return [...props.events].sort((a, b) => {
    const nextA = getNextAvailableDate(a.id) ?? a.start_date
    const nextB = getNextAvailableDate(b.id) ?? b.start_date
    // Events with future dates first, then by proximity
    const diffA = nextA >= todayStr.value ? 0 : 1
    const diffB = nextB >= todayStr.value ? 0 : 1
    if (diffA !== diffB) return diffA - diffB
    return nextA.localeCompare(nextB)
  })
})

const visibleEvents = computed(() => {
  return sortedEvents.value.slice(0, visibleCount.value)
})

const hasMore = computed(() => {
  return visibleCount.value < props.events.length
})

function getNextAvailableDate(eventId: string): string | null {
  const slots = slotsByEvent.value.get(eventId)
  if (!slots) return null
  let earliest: string | null = null
  for (const slot of slots) {
    if (slot.date < todayStr.value) continue
    if (slot.max_bookings && (slot.current_bookings ?? 0) >= slot.max_bookings) continue
    if (!earliest || slot.date < earliest) {
      earliest = slot.date
    }
  }
  return earliest
}

function getInitialDate(eventId: string): Date {
  if (props.focusMode !== 'first-available') return today.value
  const nextDate = getNextAvailableDate(eventId)
  if (!nextDate) return today.value
  const [y, m, d] = nextDate.split('-').map(Number)
  return new Date(y, m - 1, d)
}

async function loadSlotsForEvents(eventIds: string[]) {
  const toLoad = eventIds.filter((id) => !loadedEventIds.value.has(id))
  if (toLoad.length === 0) return

  const results = await Promise.allSettled(
    toLoad.map((eventId) =>
      get<{ data: DutySlotListResponse }>({
        url: '/duty-slots/',
        query: { event_id: eventId, limit: 200 },
      }),
    ),
  )

  const map = new Map(slotsByEvent.value)
  for (let i = 0; i < toLoad.length; i++) {
    const result = results[i]
    const eventId = toLoad[i]
    if (result.status === 'fulfilled') {
      map.set(eventId, result.value.data.items)
    } else {
      map.set(eventId, [])
    }
    loadedEventIds.value.add(eventId)
  }
  slotsByEvent.value = map
}

async function loadInitialPage() {
  if (props.events.length === 0) return
  loadingSlots.value = true
  visibleCount.value = PAGE_SIZE
  slotsByEvent.value = new Map()
  loadedEventIds.value = new Set()
  try {
    // Pre-sort by start_date, load slots for first page
    const initial = [...props.events]
      .sort((a, b) => a.start_date.localeCompare(b.start_date))
      .slice(0, PAGE_SIZE)
    await loadSlotsForEvents(initial.map((e) => e.id))
  } catch (error) {
    toastApiError(error)
  } finally {
    loadingSlots.value = false
  }
}

async function loadMoreEvents() {
  if (loadingMore.value || !hasMore.value) return
  loadingMore.value = true
  try {
    const prevCount = visibleCount.value
    visibleCount.value = Math.min(visibleCount.value + PAGE_SIZE, props.events.length)
    // Load slots for newly visible events
    const newEvents = sortedEvents.value.slice(prevCount, visibleCount.value)
    await loadSlotsForEvents(newEvents.map((e) => e.id))
  } catch (error) {
    toastApiError(error)
  } finally {
    loadingMore.value = false
  }
}

function setupObserver() {
  if (observer) observer.disconnect()
  observer = new IntersectionObserver(
    (entries) => {
      if (entries[0]?.isIntersecting && hasMore.value && !loadingMore.value) {
        loadMoreEvents()
      }
    },
    { rootMargin: '200px' },
  )
  if (sentinelRef.value) observer.observe(sentinelRef.value)
}

watch(
  () => props.events,
  async () => {
    await loadInitialPage()
    await nextTick()
    setupObserver()
  },
)

onMounted(async () => {
  await loadInitialPage()
  await nextTick()
  setupObserver()
})

onBeforeUnmount(() => {
  observer?.disconnect()
})
</script>

<template>
  <div v-if="events.length === 0" class="py-12 text-center text-muted-foreground">
    {{ t('duties.events.empty') }}
  </div>

  <div v-else-if="loadingSlots" class="py-12 text-center text-muted-foreground">
    {{ t('common.states.loading') }}
  </div>

  <div v-else class="space-y-3">
    <EventQuickViewCard
      v-for="event in visibleEvents"
      :key="event.id"
      :event="event"
      :slots="slotsByEvent.get(event.id) ?? []"
      :initial-start-date="getInitialDate(event.id)"
      :visible-days="5"
      :hide-full-slots="hideFullSlots"
      @navigate="emit('navigate', $event)"
      @delete="emit('delete', $event)"
      @click-slot="(slotId, ev) => emit('clickSlot', slotId, ev)"
    />

    <!-- Infinite scroll sentinel -->
    <div v-if="hasMore" ref="sentinelRef" class="flex items-center justify-center py-4">
      <Loader2 v-if="loadingMore" class="h-5 w-5 animate-spin text-muted-foreground" />
    </div>

    <!-- End of list -->
    <p v-else class="py-4 text-center text-xs text-muted-foreground">
      {{ t('duties.events.quickView.noMore') }}
    </p>
  </div>
</template>
