<script setup lang="ts">
import { computed } from 'vue'

import { type MarkerKind, markerIcon } from '@/lib/venue-map'

/**
 * One marker on a venue plan, as an SVG `<g>` for use inside an `<svg>` whose
 * user space is image units.
 *
 * `x`/`y` are image units (normalised × image size). `scale` is the current
 * image units per CSS pixel (`usePanZoom().unitsPerPixel`), so the marker is
 * drawn at a constant screen size whatever the zoom: the glyph is designed at
 * 26 px across (plus a 2px ring in the map's pill colour) and its centre sits exactly on the point.
 *
 * Attributes fall through to the `<g>`, so a parent makes it interactive with
 * `role="button" tabindex="0" :aria-label @click @keydown`. Keyboard focus
 * shows a ring (`:focus-visible`).
 */
const props = withDefaults(
  defineProps<{
    kind: MarkerKind | string
    x: number
    y: number
    scale?: number
    /** The hover hint (`VenuePinHint`, via `data-hint`), and below the marker with `showLabel`. */
    label?: string | null
    showLabel?: boolean
    selected?: boolean
    /** Draws a primary-colour ring — "your shift is here". */
    highlighted?: boolean
  }>(),
  { scale: 1, label: null, showLabel: false, selected: false, highlighted: false },
)

const icon = computed(() => markerIcon(props.kind))

// Literal class names so Tailwind's scanner emits them. Locations use the
// map's highlight colour; facilities get the colours people expect on a site
// plan, each dark enough that the white icon keeps >= 4.5:1 on it.
const KIND_CLASSES: Record<string, { body: string; icon: string }> = {
  location: { body: 'fill-map-highlight', icon: 'text-map-pill' },
  entrance: { body: 'fill-emerald-700', icon: 'text-white' },
  info_desk: { body: 'fill-sky-700', icon: 'text-white' },
  first_aid: { body: 'fill-red-600', icon: 'text-white' },
  toilets: { body: 'fill-slate-600', icon: 'text-white' },
  parking: { body: 'fill-blue-700', icon: 'text-white' },
  kitchen: { body: 'fill-amber-700', icon: 'text-white' },
}
const colours = computed(() => KIND_CLASSES[props.kind] ?? KIND_CLASSES.location!)

const transform = computed(() => `translate(${props.x} ${props.y}) scale(${props.scale})`)
</script>

<template>
  <g
    :transform="transform"
    class="venue-marker outline-none"
    :data-kind="kind"
    :data-selected="selected || undefined"
    :data-highlighted="highlighted || undefined"
    :data-hint="label || undefined"
  >
    <circle
      v-if="highlighted"
      r="20"
      fill="none"
      class="stroke-map-highlight motion-safe:animate-pulse print:animate-none"
      stroke-width="3"
      data-testid="marker-highlight"
    />
    <circle r="18" fill="none" class="venue-marker-focus stroke-map-highlight" stroke-width="2.5" />
    <circle
      :r="selected ? 15 : 13"
      :class="[colours.body, selected ? 'stroke-map-ink' : 'stroke-map-marker-ring']"
      :stroke-width="selected ? 2.5 : 2"
      class="venue-marker-body transition-[r]"
    />
    <component
      :is="icon"
      x="-8"
      y="-8"
      :size="16"
      :stroke-width="2.25"
      :class="colours.icon"
      aria-hidden="true"
    />
    <text
      v-if="showLabel && label"
      y="30"
      text-anchor="middle"
      class="fill-map-ink stroke-map-canvas text-[11px] font-semibold"
      stroke-width="3"
      paint-order="stroke"
    >
      {{ label }}
    </text>
  </g>
</template>

<style scoped>
.venue-marker-body {
  filter: drop-shadow(0 1px 2px var(--map-shadow));
}
.venue-marker-focus {
  opacity: 0;
}
.venue-marker:focus-visible .venue-marker-focus {
  opacity: 1;
}
</style>
