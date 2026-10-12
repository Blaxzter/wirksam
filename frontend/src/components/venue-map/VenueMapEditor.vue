<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

import {
  ArrowLeft,
  ArrowRight,
  EllipsisVertical,
  ImageOff,
  Map as MapIcon,
  Maximize,
  Minus,
  Pencil,
  Plus,
  Trash2,
  X,
} from '@lucide/vue'
import { useEventListener } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthedImage } from '@/composables/useAuthedImage'
import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'
import { useLocations } from '@/composables/useLocations'
import { usePanZoom } from '@/composables/usePanZoom'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'
import { Skeleton } from '@/components/ui/skeleton'

import VenueMarkerGlyph from '@/components/venue-map/VenueMarkerGlyph.vue'
import VenueMarkerPalette from '@/components/venue-map/VenueMarkerPalette.vue'
import VenuePlanSwitcher from '@/components/venue-map/VenuePlanSwitcher.vue'
import VenuePlanUpload from '@/components/venue-map/VenuePlanUpload.vue'

import type { LocationRead, VenueMapRead, VenueMarkerRead, VenuePlanRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import {
  GENERIC_MARKER_KINDS,
  type MarkerKind,
  type Point,
  clamp01,
  markerKindLabelKey,
  planImageUrl,
  toNormalised,
} from '@/lib/venue-map'

/**
 * The venue map editor (event settings → "Map" tab).
 *
 * An event has any number of plans (the grounds, one per floor, …), each with
 * one picture and the pins on it. Here an event admin adds, renames, reorders
 * and deletes plans, uploads or replaces the picture, and places, drags,
 * relabels and removes pins.
 *
 * Works with every input:
 * - mouse: drag the plan to pan, wheel to zoom, drag a pin to move it;
 * - touch: one finger pans, two pinch, a pin follows the finger that holds it;
 * - keyboard: pins are buttons — arrows nudge the focused pin (Shift: bigger
 *   steps), Delete removes it, Escape leaves placement mode; "Put it in the
 *   middle" places a new pin without pointing.
 *
 * Pins are stored normalised (0..1), so replacing the picture keeps them.
 */
const props = defineProps<{
  eventId: string
}>()

const { t } = useI18n()
const { get, post, put, patch, delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()
const authStore = useAuthStore()

const { locations } = useLocations(() => props.eventId)

// ── Plans ─────────────────────────────────────────────────────────────────
const plans = ref<VenuePlanRead[]>([])
const loading = ref(true)
// A failed load is not "no plans": showing the empty state would invite an
// admin to add the plans they already have again.
const loadError = ref(false)
const selectedPlanId = ref<string | null>(null)
const plan = computed(() => plans.value.find((p) => p.id === selectedPlanId.value) ?? null)
const planIndex = computed(() => plans.value.findIndex((p) => p.id === selectedPlanId.value))

async function load() {
  loading.value = true
  loadError.value = false
  try {
    const res = await get<{ data: VenueMapRead }>({
      url: `/events/${props.eventId}/venue-map`,
    })
    plans.value = res.data.plans
    if (!plans.value.some((p) => p.id === selectedPlanId.value)) {
      selectedPlanId.value = plans.value[0]?.id ?? null
    }
  } catch (error) {
    plans.value = []
    selectedPlanId.value = null
    loadError.value = true
    toastApiError(error)
  } finally {
    loading.value = false
  }
}

watch(() => props.eventId, load, { immediate: true })

/**
 * The nav shows "Map" only while the event has a plan with a picture
 * (`venue_plan_count`), so refresh the selected event after anything that can
 * change that count. The store ignores any event other than the selected one.
 */
function refreshEventCounts() {
  return authStore.refreshSelectedEvent(props.eventId)
}

function replacePlan(updated: VenuePlanRead) {
  const index = plans.value.findIndex((p) => p.id === updated.id)
  if (index >= 0) plans.value[index] = updated
}

// Name dialog, shared by "add map" and "rename".
const nameDialog = ref<{ open: boolean; mode: 'create' | 'rename'; name: string }>({
  open: false,
  mode: 'create',
  name: '',
})
const savingName = ref(false)
const trimmedName = computed(() => nameDialog.value.name.trim())

function openCreate() {
  nameDialog.value = { open: true, mode: 'create', name: '' }
}

function openRename() {
  if (!plan.value) return
  nameDialog.value = { open: true, mode: 'rename', name: plan.value.name }
}

async function submitName() {
  const name = trimmedName.value
  if (!name || savingName.value) return
  savingName.value = true
  try {
    if (nameDialog.value.mode === 'create') {
      const res = await post<{ data: VenuePlanRead }>({
        url: `/events/${props.eventId}/venue-plans`,
        body: { name },
      })
      plans.value.push(res.data)
      selectedPlanId.value = res.data.id
      toast.success(t('mapEditor.plans.created'))
      void refreshEventCounts()
    } else if (plan.value) {
      const res = await patch<{ data: VenuePlanRead }>({
        url: `/venue-plans/${plan.value.id}`,
        body: { name },
      })
      replacePlan(res.data)
      toast.success(t('mapEditor.plans.saved'))
    }
    nameDialog.value.open = false
  } catch (error) {
    toastApiError(error)
  } finally {
    savingName.value = false
  }
}

async function deletePlan() {
  const current = plan.value
  if (!current) return
  const confirmed = await confirmDestructive({
    text: t('mapEditor.plans.deleteConfirm', { name: current.name }),
    confirmText: t('common.actions.delete'),
  })
  if (!confirmed) return
  try {
    await del({ url: `/venue-plans/${current.id}` })
    const index = plans.value.findIndex((p) => p.id === current.id)
    plans.value = plans.value.filter((p) => p.id !== current.id)
    selectedPlanId.value = plans.value[Math.min(index, plans.value.length - 1)]?.id ?? null
    toast.success(t('mapEditor.plans.deleted'))
    void refreshEventCounts()
  } catch (error) {
    toastApiError(error)
  }
}

async function movePlan(offset: -1 | 1) {
  const from = planIndex.value
  const to = from + offset
  if (from < 0 || to < 0 || to >= plans.value.length) return
  const ids = plans.value.map((p) => p.id)
  ;[ids[from], ids[to]] = [ids[to]!, ids[from]!]
  try {
    const res = await put<{ data: VenuePlanRead[] }>({
      url: `/events/${props.eventId}/venue-plans/order`,
      body: { plan_ids: ids },
    })
    plans.value = res.data
  } catch (error) {
    toastApiError(error)
  }
}

function onUploaded(updated: VenuePlanRead) {
  replacePlan(updated)
  void refreshEventCounts()
}

// ── Canvas ────────────────────────────────────────────────────────────────
const width = computed(() => plan.value?.image_width ?? 0)
const height = computed(() => plan.value?.image_height ?? 0)

const rootRef = ref<HTMLElement | null>(null)
const svgRef = ref<SVGSVGElement | null>(null)
const canvasRef = ref<HTMLElement | null>(null)
const panZoom = usePanZoom(svgRef, { width, height })
const { viewBoxAttr, unitsPerPixel, isGesturing } = panZoom

const {
  src,
  loading: imageLoading,
  error: imageError,
} = useAuthedImage(() => planImageUrl(plan.value))

const markers = computed<VenueMarkerRead[]>(() => plan.value?.markers ?? [])
const locationNames = computed(() => new Map(locations.value.map((l) => [l.id, l.name])))
const placedLocationIds = computed(() =>
  markers.value.flatMap((m) => (m.location_id ? [m.location_id] : [])),
)

function markerName(marker: VenueMarkerRead): string {
  const name = marker.location_id ? locationNames.value.get(marker.location_id) : null
  if (name) return name
  const kind = t(markerKindLabelKey(marker.kind))
  return marker.label ? `${marker.label} (${kind})` : kind
}

// ── Placement ─────────────────────────────────────────────────────────────
type Placing = { key: string; kind: MarkerKind; locationId: string | null; name: string }
const placing = ref<Placing | null>(null)
const creating = ref(false)

function startPlacing(next: Placing) {
  placing.value = placing.value?.key === next.key ? null : next
  selectedMarkerId.value = null
  // On a phone the palette sits below the map; bring the map back into view.
  if (placing.value) {
    void nextTick(() => canvasRef.value?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' }))
  }
}

function pickLocation(location: LocationRead) {
  startPlacing({
    key: `location:${location.id}`,
    kind: 'location',
    locationId: location.id,
    name: location.name,
  })
}

function pickKind(kind: Exclude<MarkerKind, 'location'>) {
  startPlacing({ key: `kind:${kind}`, kind, locationId: null, name: t(markerKindLabelKey(kind)) })
}

/** Focus an element of this editor after the next render (it may not exist yet). */
function focusLater(selector: string) {
  void nextTick(() =>
    rootRef.value
      ?.querySelector<HTMLElement | SVGElement>(selector)
      ?.focus({ preventScroll: true }),
  )
}

function cancelPlacing() {
  const item = placing.value
  placing.value = null
  // The banner and its focused button are gone; go back to where placement began.
  if (item) focusLater(`[data-testid="palette-${item.key.replace(':', '-')}"]`)
}

async function placeAt(point: Point) {
  const item = placing.value
  const current = plan.value
  if (!item || !current || creating.value) return
  creating.value = true
  try {
    const res = await post<{ data: VenueMarkerRead }>({
      url: `/venue-plans/${current.id}/markers`,
      body: { kind: item.kind, location_id: item.locationId, x: point.x, y: point.y },
    })
    ;(current.markers ??= []).push(res.data)
    placing.value = null
    selectedMarkerId.value = res.data.id
    // Focus the new pin, so the arrow keys nudge it straight away; the banner
    // that held focus has just gone.
    focusLater(`[data-testid="map-marker-${res.data.location_id ?? res.data.id}"]`)
    toast.success(t('mapEditor.place.added'))
  } catch (error) {
    toastApiError(error)
  } finally {
    creating.value = false
  }
}

/** A click (or tap) on the plan, not on a pin, while placing: put the pin there. */
function onCanvasClick(event: MouseEvent) {
  // The click that ends a pan is neither a placement nor a deselect.
  if (isGesturing.value) return
  if (!placing.value) {
    selectedMarkerId.value = null
    return
  }
  const point = panZoom.clientToSvg(event.clientX, event.clientY)
  if (point.x < 0 || point.y < 0 || point.x > width.value || point.y > height.value) return
  void placeAt(toNormalised(point, width.value, height.value))
}

/** Keyboard (and imprecise fingers): place in the middle of the view, then nudge. */
function placeInCentre() {
  const vb = panZoom.viewBox.value
  void placeAt(toNormalised({ x: vb.x + vb.w / 2, y: vb.y + vb.h / 2 }, width.value, height.value))
}

useEventListener(document, 'keydown', (event: KeyboardEvent) => {
  if (event.key === 'Escape' && placing.value) cancelPlacing()
})

// ── Selected pin ──────────────────────────────────────────────────────────
const selectedMarkerId = ref<string | null>(null)
const selectedMarker = computed(
  () => markers.value.find((m) => m.id === selectedMarkerId.value) ?? null,
)
const labelDraft = ref('')

watch(selectedMarker, (marker) => {
  labelDraft.value = marker?.label ?? ''
})

watch(selectedPlanId, () => {
  placing.value = null
  selectedMarkerId.value = null
  panZoom.reset()
})

/** PATCH a pin; on failure put back what `revert` restores and say why. */
async function patchMarker(
  marker: VenueMarkerRead,
  body: Partial<Pick<VenueMarkerRead, 'kind' | 'label' | 'x' | 'y'>>,
  revert: () => void,
) {
  try {
    const res = await patch<{ data: VenueMarkerRead }>({
      url: `/venue-markers/${marker.id}`,
      body,
    })
    marker.kind = res.data.kind
    marker.label = res.data.label
  } catch (error) {
    revert()
    toastApiError(error)
  }
}

function saveLabel() {
  const marker = selectedMarker.value
  if (!marker || marker.kind === 'location') return
  const label = labelDraft.value.trim() || null
  if (label === (marker.label ?? null)) return
  const previous = marker.label ?? null
  marker.label = label
  void patchMarker(marker, { label }, () => {
    marker.label = previous
    labelDraft.value = previous ?? ''
  })
}

function onKindChange(event: Event) {
  const marker = selectedMarker.value
  if (!marker || marker.kind === 'location') return
  const kind = (event.target as HTMLSelectElement).value as MarkerKind
  if (kind === marker.kind) return
  const previous = marker.kind
  marker.kind = kind
  void patchMarker(marker, { kind }, () => (marker.kind = previous))
}

async function deleteMarker(marker: VenueMarkerRead) {
  const confirmed = await confirmDestructive({
    text: t('mapEditor.marker.deleteConfirm', { name: markerName(marker) }),
    confirmText: t('common.actions.delete'),
  })
  if (!confirmed) return
  const current = plan.value
  try {
    await del({ url: `/venue-markers/${marker.id}` })
    if (current?.markers) current.markers = current.markers.filter((m) => m.id !== marker.id)
    if (selectedMarkerId.value === marker.id) selectedMarkerId.value = null
  } catch (error) {
    toastApiError(error)
  }
}

// ── Dragging a pin ────────────────────────────────────────────────────────
/** Movement (CSS px) before a press on a pin becomes a drag. */
const DRAG_THRESHOLD = 4
let drag: {
  marker: VenueMarkerRead
  pointerId: number
  start: Point
  origin: Point
  moved: boolean
} | null = null
const draggingId = ref<string | null>(null)

function onMarkerPointerDown(event: PointerEvent, marker: VenueMarkerRead) {
  if (event.pointerType === 'mouse' && event.button !== 0) return
  // Keep the plan from panning underneath.
  event.stopPropagation()
  selectedMarkerId.value = marker.id
  try {
    ;(event.currentTarget as Element).setPointerCapture(event.pointerId)
  } catch {
    // Pointer already gone; the drag simply does not start.
  }
  drag = {
    marker,
    pointerId: event.pointerId,
    start: { x: event.clientX, y: event.clientY },
    origin: { x: marker.x, y: marker.y },
    moved: false,
  }
}

function onMarkerPointerMove(event: PointerEvent) {
  if (!drag || event.pointerId !== drag.pointerId) return
  event.stopPropagation()
  if (!drag.moved) {
    const distance = Math.hypot(event.clientX - drag.start.x, event.clientY - drag.start.y)
    if (distance <= DRAG_THRESHOLD) return
    drag.moved = true
    draggingId.value = drag.marker.id
  }
  const point = toNormalised(
    panZoom.clientToSvg(event.clientX, event.clientY),
    width.value,
    height.value,
  )
  drag.marker.x = point.x
  drag.marker.y = point.y
}

function onMarkerPointerUp(event: PointerEvent) {
  if (!drag || event.pointerId !== drag.pointerId) return
  event.stopPropagation()
  const { marker, origin, moved } = drag
  drag = null
  draggingId.value = null
  if (!moved) return
  if (event.type === 'pointercancel') {
    marker.x = origin.x
    marker.y = origin.y
    return
  }
  void patchMarker(marker, { x: marker.x, y: marker.y }, () => {
    marker.x = origin.x
    marker.y = origin.y
  })
}

// ── Keyboard ──────────────────────────────────────────────────────────────
const NUDGE = 0.005
const NUDGE_LARGE = 0.02
const NUDGE_SAVE_DELAY = 400
// A burst of arrow presses is one PATCH; the origin is where the burst began.
const nudgeTimers = new Map<string, ReturnType<typeof setTimeout>>()
const nudgeOrigins = new Map<string, { marker: VenueMarkerRead; origin: Point }>()

function flushNudge(id: string) {
  clearTimeout(nudgeTimers.get(id))
  nudgeTimers.delete(id)
  const pending = nudgeOrigins.get(id)
  if (!pending) return
  nudgeOrigins.delete(id)
  const { marker, origin } = pending
  void patchMarker(marker, { x: marker.x, y: marker.y }, () => {
    marker.x = origin.x
    marker.y = origin.y
  })
}

function nudge(marker: VenueMarkerRead, dx: number, dy: number) {
  if (!nudgeOrigins.has(marker.id)) {
    nudgeOrigins.set(marker.id, { marker, origin: { x: marker.x, y: marker.y } })
  }
  marker.x = clamp01(marker.x + dx)
  marker.y = clamp01(marker.y + dy)
  clearTimeout(nudgeTimers.get(marker.id))
  nudgeTimers.set(
    marker.id,
    setTimeout(() => flushNudge(marker.id), NUDGE_SAVE_DELAY),
  )
}

const ARROWS: Record<string, Point> = {
  ArrowLeft: { x: -1, y: 0 },
  ArrowRight: { x: 1, y: 0 },
  ArrowUp: { x: 0, y: -1 },
  ArrowDown: { x: 0, y: 1 },
}

function onMarkerKey(event: KeyboardEvent, marker: VenueMarkerRead) {
  const arrow = ARROWS[event.key]
  if (arrow) {
    event.preventDefault()
    const step = event.shiftKey ? NUDGE_LARGE : NUDGE
    nudge(marker, arrow.x * step, arrow.y * step)
    return
  }
  if (event.key === 'Delete' || event.key === 'Backspace') {
    event.preventDefault()
    void deleteMarker(marker)
  } else if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    selectedMarkerId.value = marker.id
  } else if (event.key === 'Escape') {
    selectedMarkerId.value = null
  }
}

// Don't lose a nudge that is still waiting for its debounce.
onBeforeUnmount(() => {
  for (const id of [...nudgeTimers.keys()]) flushNudge(id)
})
</script>

<template>
  <div ref="rootRef" class="space-y-4" data-testid="venue-map-editor">
    <div class="space-y-1">
      <h2 class="text-lg font-semibold">{{ t('mapEditor.settings.title') }}</h2>
      <p class="text-muted-foreground text-sm">{{ t('mapEditor.settings.description') }}</p>
    </div>

    <Skeleton v-if="loading" class="h-80 w-full" />

    <div
      v-else-if="loadError"
      class="flex flex-col items-center gap-3 rounded-lg border border-dashed p-8 text-center"
      role="alert"
      data-testid="map-editor-error"
    >
      <p class="text-muted-foreground text-sm">{{ t('mapEditor.plans.loadError') }}</p>
      <Button variant="outline" data-testid="map-editor-retry" @click="load">
        {{ t('venueMap.view.retry') }}
      </Button>
    </div>

    <div
      v-else-if="plans.length === 0"
      class="flex flex-col items-center gap-3 rounded-lg border border-dashed p-8 text-center"
      data-testid="map-editor-empty"
    >
      <MapIcon class="text-muted-foreground size-10" aria-hidden="true" />
      <div class="space-y-1">
        <p class="font-medium">{{ t('mapEditor.plans.empty') }}</p>
        <p class="text-muted-foreground max-w-md text-sm">{{ t('mapEditor.plans.emptyHint') }}</p>
      </div>
      <Button data-testid="plan-add" @click="openCreate">
        <Plus />
        {{ t('mapEditor.plans.add') }}
      </Button>
    </div>

    <template v-else>
      <VenuePlanSwitcher v-model="selectedPlanId" :plans="plans">
        <template #trailing>
          <DropdownMenu v-if="plan">
            <DropdownMenuTrigger as-child>
              <Button
                variant="outline"
                size="icon-sm"
                :aria-label="t('mapEditor.plans.actions')"
                data-testid="plan-actions"
              >
                <EllipsisVertical />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem data-testid="plan-rename" @select="openRename">
                <Pencil />
                {{ t('mapEditor.plans.rename') }}
              </DropdownMenuItem>
              <template v-if="plans.length > 1">
                <DropdownMenuItem
                  :disabled="planIndex <= 0"
                  data-testid="plan-move-up"
                  @select="movePlan(-1)"
                >
                  <ArrowLeft />
                  {{ t('mapEditor.plans.moveUp') }}
                </DropdownMenuItem>
                <DropdownMenuItem
                  :disabled="planIndex >= plans.length - 1"
                  data-testid="plan-move-down"
                  @select="movePlan(1)"
                >
                  <ArrowRight />
                  {{ t('mapEditor.plans.moveDown') }}
                </DropdownMenuItem>
              </template>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                variant="destructive"
                data-testid="plan-delete"
                @select="deletePlan"
              >
                <Trash2 />
                {{ t('mapEditor.plans.delete') }}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            variant="outline"
            size="sm"
            :aria-label="t('mapEditor.plans.add')"
            data-testid="plan-add"
            @click="openCreate"
          >
            <Plus />
            <span class="hidden sm:inline">{{ t('mapEditor.plans.add') }}</span>
          </Button>
        </template>
      </VenuePlanSwitcher>

      <div v-if="plan && !plan.image_etag" class="h-[50dvh] min-h-64">
        <VenuePlanUpload :plan-id="plan.id" @uploaded="onUploaded" />
      </div>

      <div v-else-if="plan" class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div
          ref="canvasRef"
          class="bg-muted/30 relative h-[60dvh] min-h-72 scroll-mt-20 overflow-hidden rounded-lg border p-4"
        >
          <!-- Padding plus `overflow-visible`: a pin on the picture's edge stays whole. -->
          <svg
            ref="svgRef"
            :viewBox="viewBoxAttr"
            class="block h-full w-full touch-none overflow-visible select-none"
            :class="placing ? 'cursor-crosshair' : 'cursor-grab active:cursor-grabbing'"
            role="group"
            :aria-label="plan.name"
            :aria-busy="imageLoading || undefined"
            data-testid="editor-canvas"
            @click="onCanvasClick"
          >
            <image
              v-if="src"
              :href="src"
              x="0"
              y="0"
              :width="width"
              :height="height"
              preserveAspectRatio="none"
            />
            <VenueMarkerGlyph
              v-for="marker in markers"
              :key="marker.id"
              :kind="marker.kind"
              :x="marker.x * width"
              :y="marker.y * height"
              :scale="unitsPerPixel"
              :label="markerName(marker)"
              :selected="marker.id === selectedMarkerId"
              role="button"
              tabindex="0"
              :aria-label="markerName(marker)"
              :aria-pressed="marker.id === selectedMarkerId"
              :aria-describedby="
                marker.id === selectedMarkerId ? 'map-editor-nudge-hint' : undefined
              "
              :class="draggingId === marker.id ? 'cursor-grabbing' : 'cursor-move'"
              :data-testid="`map-marker-${marker.location_id ?? marker.id}`"
              @pointerdown="onMarkerPointerDown($event, marker)"
              @pointermove="onMarkerPointerMove($event)"
              @pointerup="onMarkerPointerUp($event)"
              @pointercancel="onMarkerPointerUp($event)"
              @click.stop
              @dblclick.stop
              @focus="selectedMarkerId = marker.id"
              @keydown="onMarkerKey($event, marker)"
            />
          </svg>

          <div v-if="imageLoading" class="absolute inset-0" role="status">
            <Skeleton class="h-full w-full rounded-none" />
            <span class="sr-only">{{ t('venueMap.canvas.loading') }}</span>
          </div>
          <div
            v-else-if="imageError"
            class="text-muted-foreground absolute inset-0 flex flex-col items-center justify-center gap-2 p-4 text-center text-sm"
            role="alert"
          >
            <ImageOff class="size-6" />
            {{ t('venueMap.canvas.error') }}
          </div>

          <div
            v-if="placing"
            class="bg-background/95 absolute inset-x-2 top-2 flex flex-wrap items-center gap-2 rounded-md border p-2 pl-3 text-sm shadow-md"
            role="status"
            data-testid="placement-banner"
          >
            <span class="min-w-0 flex-1">{{
              t('mapEditor.place.banner', { name: placing.name })
            }}</span>
            <Button
              size="sm"
              variant="secondary"
              :disabled="creating"
              data-testid="placement-centre"
              @click="placeInCentre"
            >
              {{ t('mapEditor.place.centre') }}
            </Button>
            <Button size="sm" variant="ghost" data-testid="placement-cancel" @click="cancelPlacing">
              <X />
              {{ t('mapEditor.place.cancel') }}
            </Button>
          </div>

          <div class="absolute right-2 bottom-2 flex flex-col gap-1">
            <Button
              size="icon-sm"
              variant="secondary"
              class="shadow"
              :aria-label="t('venueMap.canvas.zoomIn')"
              @click="panZoom.zoomIn()"
            >
              <Plus />
            </Button>
            <Button
              size="icon-sm"
              variant="secondary"
              class="shadow"
              :aria-label="t('venueMap.canvas.zoomOut')"
              @click="panZoom.zoomOut()"
            >
              <Minus />
            </Button>
            <Button
              size="icon-sm"
              variant="secondary"
              class="shadow"
              :aria-label="t('venueMap.canvas.reset')"
              @click="panZoom.reset()"
            >
              <Maximize />
            </Button>
          </div>
        </div>

        <aside class="space-y-4">
          <section
            v-if="selectedMarker"
            class="space-y-3 rounded-lg border p-3"
            :aria-label="t('mapEditor.marker.title')"
            data-testid="marker-panel"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <p class="text-muted-foreground text-xs">{{ t('mapEditor.marker.title') }}</p>
                <p class="truncate font-medium">{{ markerName(selectedMarker) }}</p>
              </div>
              <Button
                size="sm"
                variant="ghost"
                data-testid="marker-panel-close"
                @click="selectedMarkerId = null"
              >
                {{ t('mapEditor.marker.close') }}
              </Button>
            </div>

            <template v-if="selectedMarker.kind !== 'location'">
              <div class="space-y-1.5">
                <Label for="map-editor-marker-kind">{{ t('mapEditor.marker.kind') }}</Label>
                <NativeSelect
                  id="map-editor-marker-kind"
                  :model-value="selectedMarker.kind"
                  class="w-full"
                  data-testid="marker-kind"
                  @change="onKindChange"
                >
                  <NativeSelectOption
                    v-for="kind in GENERIC_MARKER_KINDS"
                    :key="kind"
                    :value="kind"
                  >
                    {{ t(markerKindLabelKey(kind)) }}
                  </NativeSelectOption>
                </NativeSelect>
              </div>
              <div class="space-y-1.5">
                <Label for="map-editor-marker-label">{{ t('mapEditor.marker.label') }}</Label>
                <Input
                  id="map-editor-marker-label"
                  v-model="labelDraft"
                  maxlength="120"
                  :placeholder="t('mapEditor.marker.labelPlaceholder')"
                  data-testid="marker-label"
                  @change="saveLabel"
                  @keydown.enter.prevent="saveLabel"
                />
              </div>
            </template>
            <p v-else class="text-muted-foreground text-sm">
              {{ t('mapEditor.marker.locationHint') }}
            </p>

            <p id="map-editor-nudge-hint" class="text-muted-foreground text-xs">
              {{ t('mapEditor.marker.nudgeHint') }}
            </p>

            <Button
              size="sm"
              variant="outline"
              class="text-destructive w-full"
              data-testid="marker-delete"
              @click="deleteMarker(selectedMarker)"
            >
              <Trash2 />
              {{ t('mapEditor.marker.delete') }}
            </Button>
          </section>

          <div class="rounded-lg border p-3">
            <VenueMarkerPalette
              :locations="locations"
              :placed-location-ids="placedLocationIds"
              :active="placing?.key ?? null"
              :disabled="creating"
              @pick-location="pickLocation"
              @pick-kind="pickKind"
            />
          </div>

          <div class="rounded-lg border p-3">
            <VenuePlanUpload :plan-id="plan.id" compact @uploaded="onUploaded" />
          </div>
        </aside>
      </div>
    </template>

    <ResponsiveDialog v-model:open="nameDialog.open">
      <ResponsiveDialogContent>
        <ResponsiveDialogHeader>
          <ResponsiveDialogTitle>
            {{
              nameDialog.mode === 'create'
                ? t('mapEditor.plans.addTitle')
                : t('mapEditor.plans.renameTitle')
            }}
          </ResponsiveDialogTitle>
        </ResponsiveDialogHeader>
        <ResponsiveDialogBody class="pb-2">
          <form id="map-editor-plan-name" class="space-y-1.5" @submit.prevent="submitName">
            <Label for="map-editor-plan-name-input">{{ t('mapEditor.plans.name') }}</Label>
            <Input
              id="map-editor-plan-name-input"
              v-model="nameDialog.name"
              maxlength="120"
              :placeholder="t('mapEditor.plans.namePlaceholder')"
              data-testid="plan-name-input"
            />
          </form>
        </ResponsiveDialogBody>
        <ResponsiveDialogFooter>
          <Button variant="outline" @click="nameDialog.open = false">
            {{ t('common.actions.cancel') }}
          </Button>
          <Button
            type="submit"
            form="map-editor-plan-name"
            :disabled="!trimmedName || savingName"
            data-testid="plan-name-save"
          >
            {{ t('common.actions.save') }}
          </Button>
        </ResponsiveDialogFooter>
      </ResponsiveDialogContent>
    </ResponsiveDialog>
  </div>
</template>
