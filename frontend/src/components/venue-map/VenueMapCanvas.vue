<script setup lang="ts">
import { computed, ref } from 'vue'

import { ImageOff } from '@lucide/vue'
import { until, useElementSize } from '@vueuse/core'
import { useI18n } from 'vue-i18n'

import { useAuthedImage } from '@/composables/useAuthedImage'
import { usePanZoom } from '@/composables/usePanZoom'

import { Skeleton } from '@/components/ui/skeleton'

import VenueMarkerGlyph from '@/components/venue-map/VenueMarkerGlyph.vue'
import VenueMarkerPill from '@/components/venue-map/VenueMarkerPill.vue'
import VenuePinHint from '@/components/venue-map/VenuePinHint.vue'
import VenueShapeLayer from '@/components/venue-map/VenueShapeLayer.vue'

import type { LocationRead, VenueMarkerRead, VenuePlanRead } from '@/client/types.gen'
import {
  type StaffingStatus,
  markerKindLabelKey,
  planImageUrl,
  staffingStatus,
} from '@/lib/venue-map'
import {
  type RenderShape,
  planMarkers,
  planSize,
  planSurfaceClass,
  sortShapes,
} from '@/lib/venue-shapes'

/**
 * A venue plan with its markers, read-only: pan, pinch and wheel zoom, and
 * markers you can tap (or focus and press Enter).
 *
 * The SVG's user space is plan units (`0 0 width height`: the picture's size,
 * or the blank canvas's), so marker `x`/`y` (stored normalised) are multiplied
 * by that size. Fills its parent — give that a height.
 *
 * Layers, bottom to top: the picture (if any), the drawn shapes
 * (`VenueShapeLayer`; an area linked to a place can be tapped and selects it),
 * then the markers. A place drawn as an area without a marker on this plan
 * gets a virtual pill at the area's centre (`planMarkers`). A plan with a
 * picture keeps the light map colours in dark mode (`planSurfaceClass`).
 *
 * Location markers are labelled pills (`VenueMarkerPill`) coloured by that
 * day's staffing (`staffing`, keyed by location id); the generic ones
 * (entrance, toilets, …) stay small icon badges. On a narrow screen at the
 * fitted zoom the pills shrink to their badge, so a busy plan stays readable;
 * zooming in brings the names back.
 *
 * The default slot renders inside the `<svg>` after the markers, with
 * `{ width, height, unitsPerPixel }`, for overlays drawn in image units.
 */
const props = withDefaults(
  defineProps<{
    plan: VenuePlanRead
    /** The event's locations, for marker names. */
    locations?: ReadonlyArray<LocationRead>
    /** Location ids to ring in the primary colour (e.g. "my shifts"). */
    highlightIds?: ReadonlyArray<string>
    selectedMarkerId?: string | null
    /** `false`: no gestures, markers are not buttons. */
    interactive?: boolean
    /** Print each marker's name below it. */
    showLabels?: boolean
    /** Kept for symmetry with the other map components; not used for requests. */
    eventId?: string | null
    /** That day's bookings per location id; a place without an entry has no shifts. */
    staffing?: Readonly<Record<string, { booked: number; capacity: number }>>
    /** The number shown in a location pill's badge, per location id. */
    badges?: Readonly<Record<string, number>>
  }>(),
  {
    locations: () => [],
    highlightIds: () => [],
    selectedMarkerId: null,
    interactive: true,
    showLabels: false,
    eventId: null,
    staffing: () => ({}),
    badges: () => ({}),
  },
)

const emit = defineEmits<{
  /** A marker, or the virtual marker of a tapped area (`shape:<id>` ids). */
  'select-marker': [marker: VenueMarkerRead]
  /** A tap on the plan itself, away from any marker. */
  'select-background': []
}>()

const { t } = useI18n()

const size = computed(() => planSize(props.plan))
const width = computed(() => size.value.W)
const height = computed(() => size.value.H)
const shapes = computed(() => sortShapes(props.plan.shapes ?? []))
const allMarkers = computed(() => planMarkers(props.plan))
const surfaceClass = computed(() => planSurfaceClass(props.plan))

const svgRef = ref<SVGSVGElement | null>(null)
const panZoom = usePanZoom(svgRef, {
  width,
  height,
  enabled: () => props.interactive,
})
const { viewBoxAttr, unitsPerPixel, isGesturing } = panZoom

const rootRef = ref<HTMLElement | null>(null)
const { width: rootWidth } = useElementSize(rootRef)
/** Narrow and not zoomed in: draw location pills as their badge only. */
const compactPills = computed(() => {
  const zoom = width.value > 0 ? width.value / panZoom.viewBox.value.w : 1
  return rootWidth.value > 0 && rootWidth.value < 560 && zoom < 1.75
})

function pillStatus(marker: VenueMarkerRead): StaffingStatus {
  return marker.location_id ? staffingStatus(props.staffing[marker.location_id]) : 'none'
}

function pillCount(marker: VenueMarkerRead): string | null {
  const stat = marker.location_id ? props.staffing[marker.location_id] : null
  return stat && stat.capacity > 0 ? `${stat.booked}/${stat.capacity}` : null
}

function pillBadge(marker: VenueMarkerRead): number | null {
  return marker.location_id ? (props.badges[marker.location_id] ?? null) : null
}

const image = useAuthedImage(() => planImageUrl(props.plan))
const { src, loading, error } = image

// The blob URL exists before the browser has decoded the picture; print waits
// for the `<image>` load too.
const decodedSrc = ref<string | null>(null)
const markDecoded = () => (decodedSrc.value = src.value)

const locationNames = computed(() => new Map(props.locations.map((l) => [l.id, l.name])))
const highlighted = computed(() => new Set(props.highlightIds))

function markerName(marker: VenueMarkerRead): string {
  const name = marker.location_id ? locationNames.value.get(marker.location_id) : null
  if (name) return name
  const kind = t(markerKindLabelKey(marker.kind))
  return marker.label ? `${marker.label} (${kind})` : kind
}

/** A location pin whose place still exists is a pill; anything else a glyph. */
function isPill(marker: VenueMarkerRead) {
  return !!marker.location_id && locationNames.value.has(marker.location_id)
}

function isHighlighted(marker: VenueMarkerRead) {
  return !!marker.location_id && highlighted.value.has(marker.location_id)
}

// Generic markers first, pills over them, highlighted pills last, so they sit on top. Selection does not
// reorder: moving the focused `<g>` in the DOM would drop keyboard focus.
// Instead the selected marker is drawn once more on top, as an inert copy.
const markers = computed(() => {
  const rank = (m: VenueMarkerRead) => (isHighlighted(m) ? 2 : isPill(m) ? 1 : 0)
  return [...allMarkers.value].sort((a, b) => rank(a) - rank(b))
})
const selectedMarker = computed(
  () => allMarkers.value.find((m) => m.id === props.selectedMarkerId) ?? null,
)
/** The place whose areas get the strong highlight: the selected pill's. */
const selectedLocationId = computed(() => selectedMarker.value?.location_id ?? null)

function select(marker: VenueMarkerRead) {
  if (!props.interactive) return
  // A drag that ended on a marker is a pan, not a tap.
  if (isGesturing.value) return
  emit('select-marker', marker)
}

function onBackgroundClick(event: MouseEvent) {
  if (!props.interactive || isGesturing.value) return
  if ((event.target as Element | null)?.closest?.('.venue-marker, .vs-tappable')) return
  emit('select-background')
}

/** A tapped area selects its place: through its pill on this plan, real or virtual. */
function onShapeSelect(shape: RenderShape) {
  if (!props.interactive || isGesturing.value || !shape.location_id) return
  const marker = allMarkers.value.find(
    (m) => m.location_id === shape.location_id && m.kind === 'location',
  )
  if (marker) emit('select-marker', marker)
}

function onMarkerKey(event: KeyboardEvent, marker: VenueMarkerRead) {
  if (event.key !== 'Enter' && event.key !== ' ') return
  event.preventDefault()
  emit('select-marker', marker)
}

/** Centre a marker at `zoom`× the fitted view. */
function focusMarker(markerId: string, zoom = 3) {
  const marker = allMarkers.value.find((m) => m.id === markerId)
  if (marker) panZoom.focus(marker.x, marker.y, zoom)
}

/**
 * Resolves once the picture has been fetched and drawn, or has failed; at once
 * for a drawn plan, whose shapes come with it.
 */
async function ready() {
  await image.ready()
  if (!src.value) return
  await until(() => decodedSrc.value === src.value || !!error.value).toBe(true, {
    timeout: 5000,
  })
}

defineExpose({
  focus: panZoom.focus,
  focusMarker,
  zoomIn: panZoom.zoomIn,
  zoomOut: panZoom.zoomOut,
  reset: panZoom.reset,
  clientToSvg: panZoom.clientToSvg,
  viewBox: panZoom.viewBox,
  ready,
})
</script>

<template>
  <!-- The padding (with `overflow-visible` on the SVG) keeps a pin on the very
       edge of the picture whole: the plan is fitted inside it, the pin spills over. -->
  <!-- The extra room on top is for the pills, which stand above their point. -->
  <div
    ref="rootRef"
    class="map-ground relative h-full w-full overflow-hidden px-4 pt-10 pb-4"
    :class="surfaceClass"
    data-testid="venue-map-canvas"
  >
    <svg
      ref="svgRef"
      :viewBox="viewBoxAttr"
      class="block h-full w-full overflow-visible select-none"
      :class="interactive ? 'touch-none cursor-grab active:cursor-grabbing' : ''"
      role="group"
      :aria-label="plan.name"
      :aria-busy="loading || undefined"
      @click="onBackgroundClick"
    >
      <image
        v-if="src"
        :href="src"
        x="0"
        y="0"
        :width="width"
        :height="height"
        preserveAspectRatio="none"
        @load="markDecoded"
        @error="markDecoded"
      />
      <VenueShapeLayer
        v-if="shapes.length"
        :shapes="shapes"
        :width="width"
        :height="height"
        :units-per-pixel="unitsPerPixel"
        :interactive="interactive ? 'linked' : 'none'"
        :selected-location-id="selectedLocationId"
        :highlight-location-ids="highlightIds"
        @select-shape="onShapeSelect"
      />
      <template v-for="marker in markers" :key="marker.id">
        <VenueMarkerPill
          v-if="isPill(marker)"
          :x="marker.x * width"
          :y="marker.y * height"
          :scale="unitsPerPixel"
          :name="markerName(marker)"
          :count="pillCount(marker)"
          :status="pillStatus(marker)"
          :badge="pillBadge(marker)"
          :compact="compactPills"
          :selected="marker.id === selectedMarkerId"
          :highlighted="isHighlighted(marker)"
          :role="interactive ? 'button' : undefined"
          :tabindex="interactive ? 0 : undefined"
          :aria-label="markerName(marker)"
          :aria-pressed="interactive ? marker.id === selectedMarkerId : undefined"
          :class="interactive ? 'cursor-pointer' : ''"
          :data-testid="`map-marker-${marker.location_id ?? marker.id}`"
          @click="select(marker)"
          @keydown="onMarkerKey($event, marker)"
        />
        <VenueMarkerGlyph
          v-else
          :kind="marker.kind"
          :x="marker.x * width"
          :y="marker.y * height"
          :scale="unitsPerPixel"
          :label="markerName(marker)"
          :show-label="showLabels"
          :selected="marker.id === selectedMarkerId"
          :highlighted="isHighlighted(marker)"
          :role="interactive ? 'button' : undefined"
          :tabindex="interactive ? 0 : undefined"
          :aria-label="markerName(marker)"
          :aria-pressed="interactive ? marker.id === selectedMarkerId : undefined"
          :class="interactive ? 'cursor-pointer' : ''"
          :data-testid="`map-marker-${marker.location_id ?? marker.id}`"
          @click="select(marker)"
          @keydown="onMarkerKey($event, marker)"
        />
      </template>
      <template v-if="selectedMarker">
        <VenueMarkerPill
          v-if="isPill(selectedMarker)"
          :x="selectedMarker.x * width"
          :y="selectedMarker.y * height"
          :scale="unitsPerPixel"
          :name="markerName(selectedMarker)"
          :count="pillCount(selectedMarker)"
          :status="pillStatus(selectedMarker)"
          :badge="pillBadge(selectedMarker)"
          :compact="compactPills"
          selected
          :highlighted="isHighlighted(selectedMarker)"
          aria-hidden="true"
          class="pointer-events-none"
          data-testid="map-marker-selected-copy"
        />
        <VenueMarkerGlyph
          v-else
          :kind="selectedMarker.kind"
          :x="selectedMarker.x * width"
          :y="selectedMarker.y * height"
          :scale="unitsPerPixel"
          :label="markerName(selectedMarker)"
          :show-label="showLabels"
          selected
          :highlighted="isHighlighted(selectedMarker)"
          aria-hidden="true"
          class="pointer-events-none"
          data-testid="map-marker-selected-copy"
        />
      </template>
      <slot :width="width" :height="height" :units-per-pixel="unitsPerPixel" />
    </svg>
    <VenuePinHint :container="svgRef" />

    <div v-if="loading" class="absolute inset-0" role="status">
      <Skeleton class="h-full w-full rounded-none" />
      <span class="sr-only">{{ t('venueMap.canvas.loading') }}</span>
    </div>
    <div
      v-else-if="error"
      class="text-muted-foreground absolute inset-0 flex flex-col items-center justify-center gap-2 p-4 text-center text-sm"
      role="alert"
    >
      <ImageOff class="size-6" />
      {{ t('venueMap.canvas.error') }}
    </div>
  </div>
</template>
