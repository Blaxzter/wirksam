<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

import {
  Check,
  ChevronLeft,
  ChevronRight,
  EllipsisVertical,
  List,
  LoaderCircle,
  Map as MapIcon,
  Maximize,
  Minus,
  Pencil,
  Plus,
  Search,
  Star,
  X,
} from '@lucide/vue'
import { useEventListener, useMediaQuery } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useFormatters } from '@/composables/useFormatters'

import Button from '@/components/ui/button/Button.vue'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { Toggle } from '@/components/ui/toggle'

import VenueLocationDetails from '@/components/venue-map/VenueLocationDetails.vue'
import VenueLocationSheet from '@/components/venue-map/VenueLocationSheet.vue'
import VenueMapCanvas from '@/components/venue-map/VenueMapCanvas.vue'
import VenueMapEditor from '@/components/venue-map/VenueMapEditor.vue'
import VenuePlaceOverview from '@/components/venue-map/VenuePlaceOverview.vue'
import VenuePlanSwitcher from '@/components/venue-map/VenuePlanSwitcher.vue'

import type {
  EventRead,
  LocationRead,
  VenueLocationStat,
  VenueMapRead,
  VenueMarkerRead,
  VenuePlanRead,
} from '@/client/types.gen'
import {
  type PlaceOverviewItem,
  STAFFING_CLASSES,
  STAFFING_LEGEND,
  markerIcon,
  markerKindLabelKey,
  staffingLabelKey,
} from '@/lib/venue-map'

/**
 * The event's venue map: pick a plan, find a place, tap it to see that day's
 * staffing and shifts there and book one.
 *
 * `/app/map/:eventId?` — without the param it shows the selected event.
 * `?plan=` and `?location=` are kept in the URL, so a link (from a mini-map,
 * say) opens the right plan focused on the right place with its details open.
 * The route has one view key, so these query updates do not remount the view.
 *
 * The page fills the viewport exactly (`meta.fullHeight`): one toolbar row,
 * then the map with a side panel on a wide screen — the selected place, or
 * every place with its staffing while nothing is selected. Narrower screens
 * get the details as a bottom sheet and the list behind a menu entry.
 *
 * Event admins switch the page into editing in place ("Edit" → the venue map
 * editor, "Done" → back), no detour through the event settings.
 */

type SearchResult = {
  key: string
  label: string
  /** The plan it is on, or nothing for a location without a pin. */
  planName: string | null
  kind: string
  marker: VenueMarkerRead | null
  location: LocationRead | null
}

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { get } = useAuthenticatedClient()
const { formatDateLabel } = useFormatters()

/** Side panel and one-row toolbar from here; below, sheets and a menu. */
const isWide = useMediaQuery('(min-width: 1024px)')

const eventId = computed(
  () => (route.params.eventId as string | undefined) || authStore.selectedEventId || null,
)
const canManage = computed(() => (eventId.value ? authStore.canManageEvent(eventId.value) : false))

// === Event (for its date range) ===
const fetchedEvent = ref<EventRead | null>(null)
const event = computed<EventRead | null>(() =>
  authStore.selectedEvent?.id === eventId.value ? authStore.selectedEvent : fetchedEvent.value,
)

// === Day ===
function isoDate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
function shiftDay(day: string, delta: number): string {
  const d = new Date(day + 'T00:00:00')
  d.setDate(d.getDate() + delta)
  return isoDate(d)
}
/** Today while the event runs, else its first day. */
function defaultDay(ev: EventRead | null): string {
  const today = isoDate(new Date())
  if (!ev) return today
  return today >= ev.start_date && today <= ev.end_date ? today : ev.start_date
}

const day = ref<string | null>(null)
const canGoPrev = computed(() => !!day.value && !!event.value && day.value > event.value.start_date)
const canGoNext = computed(() => !!day.value && !!event.value && day.value < event.value.end_date)
const dayLabel = computed(() =>
  day.value ? formatDateLabel(day.value, { weekday: 'short', day: 'numeric', month: 'short' }) : '',
)

/**
 * The day the staffing on screen belongs to. Right after a day switch it is
 * still the previous one until the new numbers arrive, so the legend, the list
 * and the details keep naming the day their numbers are for.
 */
const dataDay = computed(() => mapData.value?.on ?? day.value)
const dataDayLabel = computed(() =>
  dataDay.value
    ? formatDateLabel(dataDay.value, { weekday: 'short', day: 'numeric', month: 'short' })
    : '',
)
/** A day switch is loading: the map still shows the previous day's numbers. */
const dayPending = computed(() => !!mapData.value && !!day.value && mapData.value.on !== day.value)

function moveDay(delta: number) {
  if (!day.value) return
  day.value = shiftDay(day.value, delta)
  void loadMap()
}

// === Map data ===
const mapData = ref<VenueMapRead | null>(null)
const loading = ref(false)
const loadError = ref(false)
let requestSeq = 0

async function loadMap({ quiet = false } = {}) {
  const id = eventId.value
  const on = day.value
  if (!id || !on) return
  const seq = ++requestSeq
  if (!quiet) loading.value = true
  loadError.value = false
  try {
    const res = await get<{ data: VenueMapRead }>({
      url: `/events/${id}/venue-map`,
      query: { on },
    })
    if (seq !== requestSeq) return
    mapData.value = res.data
  } catch {
    if (seq !== requestSeq) return
    if (!quiet) mapData.value = null
    loadError.value = !quiet
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

/** Load the event (if it is not the selected one), settle the day, load the map. */
async function init() {
  const id = eventId.value
  // Drops a map request still in flight for the previous event.
  requestSeq++
  loading.value = false
  loadError.value = false
  mapData.value = null
  fetchedEvent.value = null
  day.value = null
  refreshEditedEvent()
  editing.value = false
  clearSelection()
  if (!id) return
  if (authStore.selectedEvent?.id !== id) {
    loading.value = true
    try {
      const res = await get<{ data: EventRead }>({ url: `/events/${id}` })
      if (eventId.value !== id) return
      fetchedEvent.value = res.data
    } catch {
      if (eventId.value !== id) return
      loading.value = false
      loadError.value = true
      return
    }
  }
  day.value = defaultDay(event.value)
  await loadMap()
  applyDeepLink()
}

/** Retry what failed: the map for the day on screen, or the event itself. */
function retry() {
  if (day.value) void loadMap()
  else void init()
}

// Switching event in the header while on another event's map: follow it.
watch(
  () => authStore.selectedEventId,
  (next, prev) => {
    if (next && next !== prev && route.params.eventId && route.params.eventId !== next) {
      void router.replace({ name: 'event-map' })
    }
  },
)

// === Plans ===
const plans = computed<VenuePlanRead[]>(() =>
  (mapData.value?.plans ?? []).filter((p) => p.image_etag && p.image_width && p.image_height),
)
const locations = computed(() => mapData.value?.locations ?? [])
const locationsById = computed(() => new Map(locations.value.map((l) => [l.id, l])))

const planId = ref<string | null>(null)
const activePlan = computed(
  () => plans.value.find((p) => p.id === planId.value) ?? plans.value[0] ?? null,
)

// Keep the chosen plan valid as data arrives; `?plan=` wins when it exists.
watch(
  plans,
  (list) => {
    // The current choice survives a reload (day change, booking); a fresh
    // load takes `?plan=`.
    const current = list.find((p) => p.id === planId.value)
    const fromQuery = list.find((p) => p.id === route.query.plan)
    planId.value = (current ?? fromQuery ?? list[0])?.id ?? null
  },
  { immediate: true },
)

function setQuery(patch: Record<string, string | undefined>) {
  const query = { ...route.query, ...patch }
  for (const key of Object.keys(patch)) if (patch[key] === undefined) delete query[key]
  void router.replace({ query })
}

function onPlanChange(id: string | null) {
  if (!id || id === planId.value) return
  planId.value = id
  clearSelection()
  setQuery({ plan: id, location: undefined })
}

// === Staffing ===
const statsById = computed(
  () =>
    new Map<string, VenueLocationStat>(
      (mapData.value?.location_stats ?? []).map((s) => [s.location_id, s]),
    ),
)
const staffing = computed(() => Object.fromEntries(statsById.value))

/** Every place, by name; its position is the number on its pill. */
/** Each location's pin: the one on the active plan, else the first elsewhere. */
const markerByLocation = computed(() => {
  const byLocation = new Map<string, VenueMarkerRead>()
  for (const plan of plans.value) {
    for (const marker of plan.markers ?? []) {
      if (!marker.location_id) continue
      const existing = byLocation.get(marker.location_id)
      if (!existing || (marker.plan_id === planId.value && existing.plan_id !== planId.value)) {
        byLocation.set(marker.location_id, marker)
      }
    }
  }
  return byLocation
})

function markerForLocation(locationId: string): VenueMarkerRead | null {
  return markerByLocation.value.get(locationId) ?? null
}

const placeItems = computed<PlaceOverviewItem[]>(() => {
  const mine = new Set(mapData.value?.my_location_ids ?? [])
  return [...locations.value]
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((location, index) => ({
      location,
      badge: index + 1,
      stat: statsById.value.get(location.id) ?? null,
      pinned: !!markerForLocation(location.id),
      mine: mine.has(location.id),
    }))
})
const badges = computed(() =>
  Object.fromEntries(placeItems.value.map((item) => [item.location.id, item.badge])),
)

// === Highlights ===
const myShiftsOn = ref(true)
const highlightIds = computed(() =>
  myShiftsOn.value ? (mapData.value?.my_location_ids ?? []) : [],
)

// === Canvas ===
const canvas = ref<InstanceType<typeof VenueMapCanvas> | null>(null)
const selectedMarkerId = ref<string | null>(null)

// === Selection: side panel on a wide screen, sheet or card below ===
const selectedLocation = ref<LocationRead | null>(null)
const genericMarker = ref<VenueMarkerRead | null>(null)
const overviewOpen = ref(false)

const selectedStat = computed(() =>
  selectedLocation.value ? (statsById.value.get(selectedLocation.value.id) ?? null) : null,
)

function clearSelection() {
  openedFromOverview = false
  selectedLocation.value = null
  genericMarker.value = null
  selectedMarkerId.value = null
}

/** The bottom sheet is the narrow screen's panel: open while a place is selected. */
const sheetOpen = computed({
  get: () => !isWide.value && !!selectedLocation.value,
  set: (open: boolean) => {
    if (!open) clearSelection()
  },
})

function openLocation(location: LocationRead) {
  genericMarker.value = null
  selectedLocation.value = location
  // Plan and location in one replace: two back-to-back replaces would each
  // start from the same old query, and the second would drop the first.
  if (route.query.location !== location.id || route.query.plan !== planId.value) {
    setQuery({ location: location.id, plan: planId.value ?? undefined })
  }
}

watch(selectedLocation, (location) => {
  if (!location && route.query.location) setQuery({ location: undefined })
})

function onSelectMarker(marker: VenueMarkerRead) {
  selectedMarkerId.value = marker.id
  const location = marker.location_id ? locationsById.value.get(marker.location_id) : null
  if (location) {
    openLocation(location)
  } else {
    selectedLocation.value = null
    genericMarker.value = marker
  }
}

/** Switch to the marker's plan, centre it and select it. */
async function showMarker(marker: VenueMarkerRead) {
  if (marker.plan_id !== planId.value) {
    planId.value = marker.plan_id
    // A location marker writes `?plan=` with `?location=` (openLocation).
    if (!marker.location_id) setQuery({ plan: marker.plan_id, location: undefined })
    // The canvas is keyed by plan: wait for the new one to mount.
    await nextTick()
  }
  await nextTick()
  canvas.value?.focusMarker(marker.id, 3)
  onSelectMarker(marker)
}

/** A place picked from the list: show its pin if it has one, and its details. */
async function selectPlace(location: LocationRead) {
  overviewOpen.value = false
  const marker = markerForLocation(location.id)
  if (marker) await showMarker(marker)
  else openLocation(location)
}

// === Focus in the side panel ===
// Picking a row swaps the list for the details (and Back swaps it back), which
// unmounts the focused button. Move focus to what replaced it, so a keyboard
// or screen reader user is not dropped at the top of the document.
const panelEl = ref<HTMLElement | null>(null)
/** The shown details were opened from the list: Back returns to its row. */
let openedFromOverview = false

function focusIn(selector: string): boolean {
  const el = panelEl.value?.querySelector<HTMLElement>(selector)
  el?.focus()
  return !!el
}

async function selectFromPanel(location: LocationRead) {
  await selectPlace(location)
  openedFromOverview = true
  await nextTick()
  focusIn('[data-testid="location-sheet-title"]')
}

/** Back (or Escape) in the side panel: close the details, focus where they came from. */
async function closePanel() {
  const locationId = selectedLocation.value?.id
  const markerId = selectedMarkerId.value
  const fromOverview = openedFromOverview
  clearSelection()
  await nextTick()
  if (fromOverview && locationId && focusIn(`[data-testid="map-overview-${locationId}"]`)) return
  const pin = markerId
    ? document.querySelector<HTMLElement>(`[data-testid="map-marker-${locationId ?? markerId}"]`)
    : null
  if (pin) pin.focus()
  else focusIn('[data-testid="map-overview-title"]')
}

/** `?location=` from a link: focus the pin and open the details. */
function applyDeepLink() {
  const locationId = route.query.location as string | undefined
  if (!locationId) return
  const marker = markerForLocation(locationId)
  if (marker) {
    void showMarker(marker)
    return
  }
  const location = locationsById.value.get(locationId)
  if (location) openLocation(location)
}

// A map link followed while already here (e.g. a mini-map in a shift dialog):
// the view is not remounted, so react to the new `?location=` directly.
watch(
  () => route.query.location,
  (id) => {
    if (!id || !mapData.value) return
    if (selectedLocation.value?.id === id) return
    applyDeepLink()
  },
)

// Escape closes the side panel's details, like it closes a sheet. Capture
// phase, so an open dialog or menu (which Escape closes first) is still there
// to be seen.
useEventListener(
  window,
  'keydown',
  (e: KeyboardEvent) => {
    if (e.key !== 'Escape' || !isWide.value || editing.value) return
    if (!selectedLocation.value && !genericMarker.value) return
    const target = e.target as HTMLElement | null
    if (target?.closest?.('input, textarea, select, [contenteditable="true"]')) return
    if (document.querySelector('[role="dialog"][data-state="open"], [role="menu"]')) return
    void closePanel()
  },
  { capture: true },
)

function onBooked() {
  void loadMap({ quiet: true })
}

// === Editing in place (event admins) ===
const editing = ref(false)
/** The event the editor saved something for since editing began. */
let editedEventId: string | null = null

function startEditing() {
  clearSelection()
  editing.value = true
}

function onEditorChanged() {
  editedEventId = eventId.value
}

/** The event's plan count (header, settings) follows the edits. */
function refreshEditedEvent() {
  if (editedEventId) void authStore.refreshSelectedEvent(editedEventId)
  editedEventId = null
}

function finishEditing() {
  editing.value = false
  // Plans, pins or pictures may have changed: fetch the map afresh.
  void loadMap({ quiet: !!mapData.value })
  refreshEditedEvent()
}

// Left while editing (sidebar, another page) instead of pressing Done.
onBeforeUnmount(refreshEditedEvent)

// === Search ===
const searchQuery = ref('')
const searchFocused = ref(false)
const activeResult = ref(0)

const planNames = computed(() => new Map(plans.value.map((p) => [p.id, p.name])))

const searchResults = computed<SearchResult[]>(() => {
  const q = searchQuery.value.trim().toLocaleLowerCase()
  if (!q) return []
  const results: SearchResult[] = []
  for (const location of locations.value) {
    if (!location.name.toLocaleLowerCase().includes(q)) continue
    const marker = markerForLocation(location.id)
    results.push({
      key: `location-${location.id}`,
      label: location.name,
      planName: marker ? (planNames.value.get(marker.plan_id) ?? null) : null,
      kind: 'location',
      marker,
      location,
    })
  }
  for (const plan of plans.value) {
    for (const marker of plan.markers ?? []) {
      if (marker.location_id) continue
      const kindLabel = t(markerKindLabelKey(marker.kind))
      const haystack = `${marker.label ?? ''} ${kindLabel}`.toLocaleLowerCase()
      if (!haystack.includes(q)) continue
      results.push({
        key: `marker-${marker.id}`,
        label: marker.label ? `${marker.label} (${kindLabel})` : kindLabel,
        planName: plan.name,
        kind: marker.kind,
        marker,
        location: null,
      })
    }
  }
  return results.slice(0, 20)
})

const showResults = computed(() => searchFocused.value && searchQuery.value.trim() !== '')

watch(searchQuery, () => (activeResult.value = 0))

function pickResult(result: SearchResult) {
  searchQuery.value = ''
  searchFocused.value = false
  ;(document.activeElement as HTMLElement | null)?.blur()
  if (result.marker) void showMarker(result.marker)
  else if (result.location) openLocation(result.location)
}

function onSearchKey(event: KeyboardEvent) {
  const count = searchResults.value.length
  if (event.key === 'ArrowDown' && count) {
    event.preventDefault()
    activeResult.value = (activeResult.value + 1) % count
  } else if (event.key === 'ArrowUp' && count) {
    event.preventDefault()
    activeResult.value = (activeResult.value - 1 + count) % count
  } else if (event.key === 'Enter' && count) {
    event.preventDefault()
    pickResult(searchResults.value[activeResult.value])
  } else if (event.key === 'Escape') {
    searchQuery.value = ''
  }
}

const genericMarkerTitle = computed(() => {
  const marker = genericMarker.value
  if (!marker) return ''
  return marker.label || t(markerKindLabelKey(marker.kind))
})

const legendStatuses = [...STAFFING_LEGEND, 'none'] as const

// Last, so everything init() touches is declared.
watch(eventId, () => void init(), { immediate: true })
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col gap-3" data-testid="venue-map-view">
    <h1 class="sr-only">{{ t('venueMap.title') }}</h1>

    <!-- Editing in place: the editor fills the page, "Done" brings the map back. -->
    <VenueMapEditor
      v-if="editing && eventId"
      :event-id="eventId"
      embedded
      :sandbox="!!event?.is_sandbox"
      class="min-h-0 flex-1"
      @changed="onEditorChanged"
    >
      <template #actions>
        <Button size="sm" class="shrink-0" data-testid="map-edit-done" @click="finishEditing">
          <Check />
          {{ t('venueMap.view.done') }}
        </Button>
      </template>
    </VenueMapEditor>

    <template v-else>
      <!-- One toolbar row: plans, search, my shifts, day, edit (a menu on small screens). -->
      <div
        v-if="day && (plans.length > 0 || loadError)"
        class="flex min-w-0 items-center gap-2"
        data-testid="map-toolbar"
      >
        <div v-if="plans.length > 1 && activePlan" class="hidden min-w-0 flex-1 lg:block">
          <VenuePlanSwitcher
            :model-value="activePlan.id"
            :plans="plans"
            @update:model-value="onPlanChange"
          />
        </div>
        <div v-else class="hidden flex-1 lg:block" />

        <div v-if="plans.length > 0" class="relative min-w-0 flex-1 lg:w-56 lg:flex-none">
          <Search
            class="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
          />
          <Input
            v-model="searchQuery"
            type="search"
            class="h-9 pl-8"
            role="combobox"
            autocomplete="off"
            :placeholder="t('venueMap.view.search')"
            :aria-label="t('venueMap.view.search')"
            :aria-expanded="showResults"
            aria-controls="map-search-results"
            :aria-activedescendant="
              showResults && searchResults.length ? `map-search-result-${activeResult}` : undefined
            "
            data-testid="map-search"
            @focus="searchFocused = true"
            @blur="searchFocused = false"
            @keydown="onSearchKey"
          />
          <ul
            v-if="showResults"
            id="map-search-results"
            role="listbox"
            class="bg-popover text-popover-foreground absolute top-full right-0 left-0 z-30 mt-1 max-h-72 overflow-y-auto rounded-md border p-1 shadow-md"
            data-testid="map-search-results"
          >
            <li
              v-if="searchResults.length === 0"
              class="text-muted-foreground px-2 py-3 text-center text-sm"
            >
              {{ t('venueMap.view.searchEmpty') }}
            </li>
            <li
              v-for="(result, index) in searchResults"
              :id="`map-search-result-${index}`"
              :key="result.key"
              role="option"
              :aria-selected="index === activeResult"
              class="flex cursor-pointer items-center gap-2 rounded-sm px-2 py-2 text-sm"
              :class="index === activeResult ? 'bg-accent text-accent-foreground' : ''"
              :data-testid="`map-search-result-${result.key}`"
              @mousedown.prevent
              @mouseenter="activeResult = index"
              @click="pickResult(result)"
            >
              <component
                :is="markerIcon(result.kind)"
                class="text-muted-foreground size-4 shrink-0"
              />
              <span class="min-w-0 flex-1 truncate">{{ result.label }}</span>
              <span
                v-if="result.planName && plans.length > 1"
                class="text-muted-foreground shrink-0 text-xs"
              >
                {{ result.planName }}
              </span>
            </li>
          </ul>
        </div>

        <Toggle
          v-if="plans.length > 0"
          v-model="myShiftsOn"
          variant="outline"
          class="hidden h-9 shrink-0 lg:inline-flex"
          :title="t('venueMap.view.myShiftsHint')"
          data-testid="map-my-shifts"
        >
          <Star />
          {{ t('venueMap.view.myShifts') }}
        </Toggle>

        <div
          class="flex shrink-0 items-center"
          :class="plans.length === 0 ? 'ml-auto' : ''"
          role="group"
          :aria-label="t('venueMap.view.day.label')"
        >
          <Button
            variant="ghost"
            size="icon"
            class="size-9"
            :disabled="!canGoPrev"
            :aria-label="t('venueMap.view.day.prev')"
            data-testid="map-day-prev"
            @click="moveDay(-1)"
          >
            <ChevronLeft class="size-4" />
          </Button>
          <span
            class="relative min-w-[5.5rem] text-center text-sm font-medium tabular-nums lg:min-w-28"
            aria-live="polite"
            data-testid="map-day-label"
          >
            {{ dayLabel }}
            <LoaderCircle
              v-if="dayPending"
              class="text-muted-foreground absolute top-1/2 -right-1 size-3.5 -translate-y-1/2 animate-spin"
              aria-hidden="true"
              data-testid="map-day-loading"
            />
          </span>
          <Button
            variant="ghost"
            size="icon"
            class="size-9"
            :disabled="!canGoNext"
            :aria-label="t('venueMap.view.day.next')"
            data-testid="map-day-next"
            @click="moveDay(1)"
          >
            <ChevronRight class="size-4" />
          </Button>
        </div>

        <!-- Always in sight for admins: icon only on a small screen. -->
        <Button
          v-if="canManage"
          variant="outline"
          size="sm"
          class="h-9 shrink-0 max-lg:w-9 max-lg:px-0"
          :title="t('venueMap.view.edit')"
          data-testid="map-edit"
          @click="startEditing"
        >
          <Pencil />
          <span class="max-lg:sr-only">{{ t('venueMap.view.edit') }}</span>
        </Button>

        <!-- Small screens: what does not fit in the row. -->
        <DropdownMenu v-if="plans.length > 0">
          <DropdownMenuTrigger as-child>
            <Button
              variant="outline"
              size="icon"
              class="size-9 shrink-0 lg:hidden"
              :aria-label="t('venueMap.view.more')"
              data-testid="map-more"
            >
              <EllipsisVertical class="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" class="w-56">
            <template v-if="plans.length > 1 && activePlan">
              <DropdownMenuLabel>{{ t('venueMap.planSwitcher.label') }}</DropdownMenuLabel>
              <DropdownMenuRadioGroup
                :model-value="activePlan.id"
                @update:model-value="(id) => onPlanChange(String(id))"
              >
                <DropdownMenuRadioItem
                  v-for="p in plans"
                  :key="p.id"
                  :value="p.id"
                  :data-testid="`map-menu-plan-${p.id}`"
                >
                  {{ p.name }}
                </DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
              <DropdownMenuSeparator />
            </template>
            <DropdownMenuItem data-testid="map-menu-places" @select="overviewOpen = true">
              <List />
              {{ t('venueMap.panel.overviewTitle') }}
            </DropdownMenuItem>
            <DropdownMenuCheckboxItem
              v-model="myShiftsOn"
              data-testid="map-menu-my-shifts"
              @select.prevent
            >
              {{ t('venueMap.view.myShifts') }}
            </DropdownMenuCheckboxItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <!-- Loading -->
      <Skeleton v-if="loading && !mapData" class="min-h-0 w-full flex-1 rounded-xl" />

      <!-- Could not load -->
      <div
        v-else-if="loadError"
        class="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 rounded-xl border border-dashed p-6 text-center"
        role="alert"
      >
        <p class="text-muted-foreground text-sm">{{ t('venueMap.view.notFound') }}</p>
        <Button variant="outline" data-testid="map-retry" @click="retry">{{
          t('venueMap.view.retry')
        }}</Button>
      </div>

      <!-- No plan with a picture -->
      <div
        v-else-if="mapData && plans.length === 0"
        class="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 rounded-xl border border-dashed p-6 text-center"
        data-testid="map-empty"
      >
        <MapIcon class="text-muted-foreground size-10" />
        <p class="font-medium">{{ t('venueMap.view.empty') }}</p>
        <p class="text-muted-foreground max-w-sm text-sm">
          {{ canManage ? t('venueMap.view.emptyAdmin') : t('venueMap.view.emptyHint') }}
        </p>
        <Button v-if="canManage && eventId" data-testid="map-go-to-editor" @click="startEditing">
          {{ t('venueMap.view.goToEditor') }}
        </Button>
      </div>

      <div
        v-else-if="mapData && activePlan"
        class="bg-card flex min-h-0 flex-1 overflow-hidden rounded-xl border"
        :aria-busy="dayPending || undefined"
      >
        <!-- The map (dimmed while another day's numbers load) -->
        <div
          class="relative min-w-0 flex-1 transition-opacity"
          :class="dayPending ? 'opacity-60' : ''"
        >
          <VenueMapCanvas
            :key="activePlan.id"
            ref="canvas"
            :plan="activePlan"
            :locations="locations"
            :highlight-ids="highlightIds"
            :selected-marker-id="selectedMarkerId"
            :event-id="eventId"
            :staffing="staffing"
            :badges="badges"
            @select-marker="onSelectMarker"
            @select-background="clearSelection"
          />

          <div
            class="bg-card absolute top-3 right-3 flex flex-col overflow-hidden rounded-lg border shadow-sm"
            role="group"
            :aria-label="t('venueMap.view.mapControls')"
          >
            <Button
              variant="ghost"
              size="icon"
              class="size-10 rounded-none border-b md:size-9"
              :aria-label="t('venueMap.canvas.zoomIn')"
              data-testid="map-zoom-in"
              @click="canvas?.zoomIn()"
            >
              <Plus class="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              class="size-10 rounded-none border-b md:size-9"
              :aria-label="t('venueMap.canvas.zoomOut')"
              data-testid="map-zoom-out"
              @click="canvas?.zoomOut()"
            >
              <Minus class="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              class="size-10 rounded-none md:size-9"
              :aria-label="t('venueMap.canvas.reset')"
              data-testid="map-zoom-reset"
              @click="canvas?.reset()"
            >
              <Maximize class="size-4" />
            </Button>
          </div>

          <!-- Legend -->
          <div
            v-if="!(genericMarker && !isWide)"
            class="bg-card/95 pointer-events-none absolute bottom-3 left-3 max-w-[calc(100%-1.5rem)] space-y-1 rounded-lg border px-2.5 py-1.5 shadow-sm sm:px-3 sm:py-2"
            data-testid="map-legend"
          >
            <p
              class="text-muted-foreground text-[10px] font-semibold tracking-wider uppercase sm:text-[11px]"
            >
              {{ t('venueMap.legend.title', { day: dataDayLabel }) }}
            </p>
            <ul
              class="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] sm:block sm:space-y-0.5 sm:text-xs"
            >
              <li
                v-for="status in legendStatuses"
                :key="status"
                class="flex items-center gap-1.5 sm:gap-2"
              >
                <span
                  class="size-2.5 rounded-full"
                  :class="STAFFING_CLASSES[status].bg"
                  aria-hidden="true"
                />
                {{ t(staffingLabelKey(status)) }}
              </li>
            </ul>
          </div>

          <!-- A generic marker (entrance, toilets, …) has nothing to book: a small card is enough. -->
          <div
            v-if="genericMarker && !isWide"
            class="bg-card absolute right-3 bottom-3 left-3 flex items-center gap-3 rounded-lg border p-3 shadow-md md:right-auto md:max-w-sm"
            role="status"
            data-testid="map-marker-card"
          >
            <component :is="markerIcon(genericMarker.kind)" class="text-primary size-5 shrink-0" />
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm font-medium">{{ genericMarkerTitle }}</p>
              <p v-if="genericMarker.label" class="text-muted-foreground text-xs">
                {{ t(markerKindLabelKey(genericMarker.kind)) }}
              </p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              class="size-8 shrink-0"
              :aria-label="t('venueMap.view.close')"
              @click="clearSelection"
            >
              <X class="size-4" />
            </Button>
          </div>
        </div>

        <!-- Side panel (wide screens) -->
        <aside
          v-if="isWide"
          class="flex w-80 shrink-0 flex-col border-l xl:w-96"
          :aria-label="t('venueMap.panel.label')"
          data-testid="map-panel"
        >
          <div ref="panelEl" class="min-h-0 flex-1 overflow-y-auto p-4">
            <div v-if="selectedLocation && dataDay" class="space-y-3" data-testid="location-sheet">
              <Button
                variant="ghost"
                size="sm"
                class="text-muted-foreground -ml-2 h-7 px-2"
                data-testid="location-panel-back"
                @click="closePanel"
              >
                <ChevronLeft />
                {{ t('venueMap.panel.back') }}
              </Button>
              <VenueLocationDetails
                :location="selectedLocation"
                :day="dataDay"
                :stat="selectedStat"
                @booked="onBooked"
              />
            </div>

            <div v-else-if="genericMarker" class="space-y-3" data-testid="map-marker-card">
              <Button
                variant="ghost"
                size="sm"
                class="text-muted-foreground -ml-2 h-7 px-2"
                @click="closePanel"
              >
                <ChevronLeft />
                {{ t('venueMap.panel.back') }}
              </Button>
              <div class="flex items-start gap-3">
                <span
                  class="bg-muted flex size-10 shrink-0 items-center justify-center rounded-full"
                >
                  <component :is="markerIcon(genericMarker.kind)" class="text-primary size-5" />
                </span>
                <div class="min-w-0">
                  <p class="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                    {{ t(markerKindLabelKey(genericMarker.kind)) }}
                  </p>
                  <h2
                    class="text-xl leading-tight font-semibold tracking-tight outline-none"
                    tabindex="-1"
                  >
                    {{ genericMarkerTitle }}
                  </h2>
                </div>
              </div>
            </div>

            <VenuePlaceOverview
              v-else
              :items="placeItems"
              :day-label="dataDayLabel"
              @select="selectFromPanel"
            />
          </div>
        </aside>
      </div>
    </template>

    <!-- Narrow screens: the place as a bottom sheet, the list of places as another. -->
    <VenueLocationSheet
      v-if="dataDay && !isWide"
      v-model:open="sheetOpen"
      :location="selectedLocation"
      :stat="selectedStat"
      :day="dataDay"
      @booked="onBooked"
    />

    <ResponsiveDialog v-if="!isWide" v-model:open="overviewOpen">
      <ResponsiveDialogContent data-testid="map-overview-sheet" dialog-class="sm:max-w-md">
        <ResponsiveDialogHeader class="sr-only">
          <ResponsiveDialogTitle>{{ t('venueMap.panel.overviewTitle') }}</ResponsiveDialogTitle>
          <ResponsiveDialogDescription>
            {{ t('venueMap.panel.overviewOn', { day: dataDayLabel }) }}
          </ResponsiveDialogDescription>
        </ResponsiveDialogHeader>
        <ResponsiveDialogBody class="pb-4">
          <VenuePlaceOverview
            :items="placeItems"
            :day-label="dataDayLabel"
            @select="selectPlace"
          />
        </ResponsiveDialogBody>
      </ResponsiveDialogContent>
    </ResponsiveDialog>
  </div>
</template>
