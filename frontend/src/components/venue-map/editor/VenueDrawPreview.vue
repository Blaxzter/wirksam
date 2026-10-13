<script setup lang="ts">
import { computed, useId } from 'vue'

import type { Draft } from '@/composables/useShapeEditor'

import type { Pt } from '@/lib/venue-shape-edit'

/**
 * What is being drawn, before it is a shape: the grid, the rubber band of a
 * rect, a polygon or path in progress with its line to the pointer, a placed
 * text waiting for its words, and the point the pointer snaps to.
 *
 * Drawn in plan units inside the editor's SVG; lines and dots keep a constant
 * screen size through `unitsPerPixel`. Never takes pointer events.
 */
const props = defineProps<{
  draft: Draft | null
  snapHit: { point: Pt; kind: 'vertex' | 'grid' } | null
  width: number
  height: number
  unitsPerPixel: number
  /** Normalised grid step; the dots show only while snapping is on. */
  grid: { gx: number; gy: number } | null
}>()

const patternId = `venue-grid-${useId()}`

const upp = computed(() => props.unitsPerPixel)

/** Grid dots only while they are at least 8 px apart on screen. */
const gridSpacing = computed(() => {
  if (!props.grid) return null
  const sx = props.grid.gx * props.width
  const sy = props.grid.gy * props.height
  if (sx / upp.value < 8 || sy / upp.value < 8) return null
  return { sx, sy }
})

const toUnits = (p: readonly number[]) => [p[0]! * props.width, p[1]! * props.height] as const
const pointsAttr = (pts: readonly (readonly number[])[]) =>
  pts.map((p) => toUnits(p).join(',')).join(' ')

const rect = computed(() => {
  const d = props.draft
  if (d?.tool !== 'rect') return null
  const [a, b] = d.points
  const [x0, y0] = toUnits(a!)
  const [x1, y1] = toUnits(b!)
  return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 }
})

const line = computed(() => {
  const d = props.draft
  if (!d || (d.tool !== 'polygon' && d.tool !== 'path')) return null
  const pts = d.hover ? [...d.points, d.hover] : d.points
  return {
    tool: d.tool,
    drawn: pointsAttr(pts),
    // Where the polygon would close: from the pointer back to the first corner.
    closing:
      d.tool === 'polygon' && d.points.length >= 2 && d.hover
        ? pointsAttr([d.hover, d.points[0]!])
        : null,
    vertices: d.points.map(toUnits),
    canClose: d.tool === 'polygon' && d.points.length >= 3,
  }
})

const labelAt = computed(() => (props.draft?.tool === 'label' ? toUnits(props.draft.at) : null))
const snap = computed(() =>
  props.snapHit ? { at: toUnits(props.snapHit.point), kind: props.snapHit.kind } : null,
)
</script>

<template>
  <g class="venue-draw-preview" pointer-events="none" aria-hidden="true" data-testid="draw-preview">
    <template v-if="gridSpacing">
      <defs>
        <pattern
          :id="patternId"
          patternUnits="userSpaceOnUse"
          :width="gridSpacing.sx"
          :height="gridSpacing.sy"
        >
          <circle cx="0" cy="0" :r="1 * upp" class="fill-map-canvas-edge" />
        </pattern>
      </defs>
      <rect
        x="0"
        y="0"
        :width="width"
        :height="height"
        :fill="`url(#${patternId})`"
        data-testid="draw-grid"
      />
    </template>

    <rect
      v-if="rect"
      v-bind="rect"
      class="fill-map-select/10 stroke-map-select"
      :stroke-width="1.5 * upp"
      :stroke-dasharray="`${6 * upp} ${4 * upp}`"
      data-testid="draw-rubber-band"
    />

    <template v-if="line">
      <polygon
        v-if="line.tool === 'polygon'"
        :points="line.drawn"
        class="fill-map-select/10 stroke-none"
      />
      <polyline
        :points="line.drawn"
        fill="none"
        class="stroke-map-select"
        :stroke-width="2 * upp"
        stroke-linejoin="round"
        stroke-linecap="round"
        data-testid="draw-line"
      />
      <polyline
        v-if="line.closing"
        :points="line.closing"
        fill="none"
        class="stroke-map-select"
        :stroke-width="1 * upp"
        :stroke-dasharray="`${4 * upp} ${4 * upp}`"
      />
      <circle
        v-for="(v, i) in line.vertices"
        :key="i"
        :cx="v[0]"
        :cy="v[1]"
        :r="(i === 0 && line.canClose ? 6 : 3.5) * upp"
        class="fill-card stroke-map-select"
        :stroke-width="1.5 * upp"
        :data-testid="i === 0 ? 'draw-first-point' : undefined"
      />
    </template>

    <g v-if="labelAt" data-testid="draw-label-at">
      <line
        :x1="labelAt[0]"
        :y1="labelAt[1] - 10 * upp"
        :x2="labelAt[0]"
        :y2="labelAt[1] + 10 * upp"
        class="stroke-map-select"
        :stroke-width="2 * upp"
      />
    </g>

    <g v-if="snap" data-testid="draw-snap" :data-kind="snap.kind">
      <rect
        v-if="snap.kind === 'vertex'"
        :x="snap.at[0] - 5 * upp"
        :y="snap.at[1] - 5 * upp"
        :width="10 * upp"
        :height="10 * upp"
        fill="none"
        class="stroke-map-select"
        :stroke-width="1.5 * upp"
      />
      <circle v-else :cx="snap.at[0]" :cy="snap.at[1]" :r="3 * upp" class="fill-map-select" />
    </g>
  </g>
</template>
