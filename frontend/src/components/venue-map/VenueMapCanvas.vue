<script setup lang="ts">
import { computed, ref } from 'vue'

import { ImageOff } from '@lucide/vue'
import { until } from '@vueuse/core'
import { useI18n } from 'vue-i18n'

import { useAuthedImage } from '@/composables/useAuthedImage'
import { usePanZoom } from '@/composables/usePanZoom'

import { Skeleton } from '@/components/ui/skeleton'

import VenueMarkerGlyph from '@/components/venue-map/VenueMarkerGlyph.vue'

import type { LocationRead, VenueMarkerRead, VenuePlanRead } from '@/client/types.gen'
import { markerKindLabelKey, planImageUrl } from '@/lib/venue-map'

/**
 * A venue plan with its markers, read-only: pan, pinch and wheel zoom, and
 * markers you can tap (or focus and press Enter).
 *
 * The SVG's user space is image units (`0 0 image_width image_height`), so
 * marker `x`/`y` (stored normalised) are multiplied by the image size. Fills
 * its parent — give that a height.
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
  }>(),
  {
    locations: () => [],
    highlightIds: () => [],
    selectedMarkerId: null,
    interactive: true,
    showLabels: false,
    eventId: null,
  },
)

const emit = defineEmits<{
  'select-marker': [marker: VenueMarkerRead]
}>()

const { t } = useI18n()

const width = computed(() => props.plan.image_width ?? 0)
const height = computed(() => props.plan.image_height ?? 0)

const svgRef = ref<SVGSVGElement | null>(null)
const panZoom = usePanZoom(svgRef, {
  width,
  height,
  enabled: () => props.interactive,
})
const { viewBoxAttr, unitsPerPixel, isGesturing } = panZoom

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

function isHighlighted(marker: VenueMarkerRead) {
  return !!marker.location_id && highlighted.value.has(marker.location_id)
}

// Highlighted markers are drawn last, so they sit on top. Selection does not
// reorder: moving the focused `<g>` in the DOM would drop keyboard focus.
// Instead the selected marker is drawn once more on top, as an inert copy.
const markers = computed(() => {
  const rank = (m: VenueMarkerRead) => (isHighlighted(m) ? 1 : 0)
  return [...(props.plan.markers ?? [])].sort((a, b) => rank(a) - rank(b))
})
const selectedMarker = computed(
  () => props.plan.markers?.find((m) => m.id === props.selectedMarkerId) ?? null,
)

function select(marker: VenueMarkerRead) {
  if (!props.interactive) return
  // A drag that ended on a marker is a pan, not a tap.
  if (isGesturing.value) return
  emit('select-marker', marker)
}

function onMarkerKey(event: KeyboardEvent, marker: VenueMarkerRead) {
  if (event.key !== 'Enter' && event.key !== ' ') return
  event.preventDefault()
  emit('select-marker', marker)
}

/** Centre a marker at `zoom`× the fitted view. */
function focusMarker(markerId: string, zoom = 3) {
  const marker = props.plan.markers?.find((m) => m.id === markerId)
  if (marker) panZoom.focus(marker.x, marker.y, zoom)
}

/** Resolves once the picture has been fetched and drawn, or has failed. */
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
  <div class="relative h-full w-full overflow-hidden p-4" data-testid="venue-map-canvas">
    <svg
      ref="svgRef"
      :viewBox="viewBoxAttr"
      class="block h-full w-full overflow-visible select-none"
      :class="interactive ? 'touch-none cursor-grab active:cursor-grabbing' : ''"
      role="group"
      :aria-label="plan.name"
      :aria-busy="loading || undefined"
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
      <VenueMarkerGlyph
        v-for="marker in markers"
        :key="marker.id"
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
      <VenueMarkerGlyph
        v-if="selectedMarker"
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
      <slot :width="width" :height="height" :units-per-pixel="unitsPerPixel" />
    </svg>

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
