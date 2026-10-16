<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import { STAFFING_CLASSES, type StaffingStatus, estimateTextWidth } from '@/lib/venue-map'

/**
 * A location on a venue plan, drawn as a labelled pill standing on a short
 * stem: `[badge] Name  booked/capacity`, with the stem's tip exactly on the
 * point. For use inside an `<svg>` whose user space is image units.
 *
 * Like `VenueMarkerGlyph`, `scale` is the current image units per CSS pixel,
 * so the pill keeps its screen size whatever the zoom. The badge and the stem
 * take the colour of the place's staffing status, and so does the outline, at
 * full strength so the status reads on any ground; a selected pill is filled
 * with it. Text uses the map's own pill ink (`--map-pill-ink`), not the page
 * foreground, so a pill on a picture plan (`.map-light`) stays dark-on-light
 * in dark mode. `compact` leaves only the badge on its stem (a crowded small
 * screen), and the name moves into the hover hint (`VenuePinHint`).
 *
 * Attributes fall through to the root `<g>`, so the parent makes it a button.
 */
const props = withDefaults(
  defineProps<{
    x: number
    y: number
    scale?: number
    name: string
    /** `booked/capacity`, or nothing when the place has no shifts that day. */
    count?: string | null
    status?: StaffingStatus
    /** Shown in the badge: the place's number in the list beside the map. */
    badge?: string | number | null
    selected?: boolean
    /** Draws a primary-colour ring — "your shift is here". */
    highlighted?: boolean
    compact?: boolean
    /** The hover hint (`VenuePinHint`, via `data-hint`); defaults to the name and count. */
    title?: string | null
  }>(),
  {
    scale: 1,
    count: null,
    status: 'none',
    badge: null,
    selected: false,
    highlighted: false,
    compact: false,
    title: null,
  },
)

// Geometry in CSS px, before `scale`.
const STEM = 9
const H = 24
const BADGE_R = 8.5
const NAME_SIZE = 12.5
const COUNT_SIZE = 11.5
const PAD_LEFT = 4
const GAP = 6
const PAD_RIGHT = 10

const nameRef = ref<SVGTextElement | null>(null)
const countRef = ref<SVGTextElement | null>(null)
const measured = ref<{ name: number; count: number } | null>(null)

/** Measure the text once the browser has laid it out; fall back to an estimate. */
function measure() {
  const name = nameRef.value?.getComputedTextLength?.() ?? 0
  const count = countRef.value?.getComputedTextLength?.() ?? 0
  measured.value = name > 0 ? { name, count } : null
}

onMounted(() => {
  measure()
  // A web font that arrives late changes the widths.
  void document.fonts?.ready?.then(measure)
})
watch(
  () => [props.name, props.count, props.compact] as const,
  () => void nextTick(measure),
)

const nameWidth = computed(
  () => measured.value?.name ?? estimateTextWidth(props.name, NAME_SIZE) * 1.05,
)
const countWidth = computed(() => {
  if (!props.count) return 0
  return measured.value?.count || estimateTextWidth(props.count, COUNT_SIZE)
})

const width = computed(() => {
  if (props.compact) return H
  const badge = PAD_LEFT + BADGE_R * 2 + GAP
  const count = props.count ? GAP + countWidth.value : 0
  return Math.ceil(badge + nameWidth.value + count + PAD_RIGHT)
})

const left = computed(() => -width.value / 2)
const top = -(STEM + H)
const midY = top + H / 2
const badgeX = computed(() => (props.compact ? 0 : left.value + PAD_LEFT + BADGE_R))
const nameX = computed(() => left.value + PAD_LEFT + BADGE_R * 2 + GAP)
const countX = computed(() => nameX.value + nameWidth.value + GAP)

const colours = computed(() => STAFFING_CLASSES[props.status])

const tooltip = computed(
  () => props.title ?? (props.count ? `${props.name} · ${props.count}` : props.name),
)

const transform = computed(() => `translate(${props.x} ${props.y}) scale(${props.scale})`)
</script>

<template>
  <g
    :transform="transform"
    class="venue-marker venue-pill outline-none"
    data-kind="location"
    :data-status="status"
    :data-selected="selected || undefined"
    :data-highlighted="highlighted || undefined"
    :data-hint="tooltip"
  >
    <!-- Stem and the dot on the exact spot. -->
    <line
      x1="0"
      :y1="-STEM"
      x2="0"
      y2="-2"
      stroke-width="2"
      stroke-linecap="round"
      :class="colours.stroke"
    />
    <circle r="2.5" :class="colours.fill" class="stroke-map-pill" stroke-width="1" />

    <rect
      v-if="highlighted"
      :x="left - 4"
      :y="top - 4"
      :width="width + 8"
      :height="H + 8"
      :rx="H / 2 + 4"
      fill="none"
      class="stroke-map-highlight motion-safe:animate-pulse print:animate-none"
      stroke-width="2.5"
      data-testid="marker-highlight"
    />
    <rect
      :x="left - 3"
      :y="top - 3"
      :width="width + 6"
      :height="H + 6"
      :rx="H / 2 + 3"
      fill="none"
      class="venue-marker-focus stroke-map-highlight"
      stroke-width="2.5"
    />
    <rect
      :x="left"
      :y="top"
      :width="width"
      :height="H"
      :rx="H / 2"
      class="venue-pill-body"
      :class="selected ? [colours.fill, 'stroke-map-pill'] : ['fill-map-pill', colours.stroke]"
      stroke-width="1.5"
    />

    <circle
      :cx="badgeX"
      :cy="midY"
      :r="BADGE_R"
      :class="selected ? 'fill-staff-foreground' : colours.fill"
    />
    <text
      v-if="badge !== null && badge !== ''"
      :x="badgeX"
      :y="midY"
      text-anchor="middle"
      dominant-baseline="central"
      class="text-[10.5px] font-bold tabular-nums"
      :class="selected ? colours.fill : 'fill-staff-foreground'"
    >
      {{ badge }}
    </text>

    <template v-if="!compact">
      <text
        ref="nameRef"
        :x="nameX"
        :y="midY"
        dominant-baseline="central"
        class="text-[12.5px] font-semibold"
        :class="selected ? 'fill-staff-foreground' : 'fill-map-pill-ink'"
        data-testid="marker-name"
      >
        {{ name }}
      </text>
      <text
        v-if="count"
        ref="countRef"
        :x="countX"
        :y="midY"
        dominant-baseline="central"
        class="text-[11.5px] font-semibold tabular-nums"
        :class="selected ? 'fill-staff-foreground' : 'fill-map-pill-ink-soft'"
        data-testid="marker-count"
      >
        {{ count }}
      </text>
    </template>
  </g>
</template>

<style scoped>
.venue-pill-body {
  filter: drop-shadow(0 1px 2px var(--map-shadow));
}
.venue-marker-focus {
  opacity: 0;
}
.venue-marker:focus-visible .venue-marker-focus {
  opacity: 1;
}
</style>
