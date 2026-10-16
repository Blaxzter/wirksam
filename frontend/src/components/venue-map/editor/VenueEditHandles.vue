<script setup lang="ts">
import { computed } from 'vue'

import { useMediaQuery } from '@vueuse/core'

import type { PropGrip } from '@/composables/useShapeEditor'

import type { VenueShapeRead } from '@/client/types.gen'
import { DEFAULT_PROP_SCALE, propPlacement } from '@/lib/venue-decor'
import { pointAtAngle, propGrips, propRingRadius, resizeCursor } from '@/lib/venue-prop-handles'
import { RECT_HANDLES, edgeMidpoints, rectHandlePoint } from '@/lib/venue-shape-edit'
import { labelAnchor, labelLayout } from '@/lib/venue-shapes'

/**
 * The grips of the selected shape, drawn in plan units on top of everything:
 *
 * - a rect: eight resize handles (corners and edge midpoints);
 * - a polygon or path: one handle per vertex, plus a small "+" on every edge
 *   that inserts a vertex there when pressed;
 * - a decoration (prop): a round rotate grip on a stalk beyond the selection
 *   ring (the shape layer draws the ring), pointing where the glyph's top
 *   points, and a square resize grip on the ring at its bottom right. Both
 *   turn with the glyph. While one is dragged (`activeGrip`) a small badge on
 *   the far side of the glyph — away from the finger — shows the angle or
 *   size. The glyph itself is moved by dragging it;
 * - any other shape with a caption except a text: a "T" handle that moves the
 *   caption (`label_x`/`label_y`); it sits just below the caption, and the
 *   caption follows the pointer's movement.
 *
 * The handles only *mark* where a press should go: each carries a
 * `data-handle` attribute (`resize:nw`, `vertex:2`, `insert:0`, `label`,
 * `rotate`, `scale`) that the editor reads from the event target. Every size
 * is in CSS pixels times `unitsPerPixel`, so the grips keep their size on
 * screen at any zoom. On a coarse pointer each gets an invisible hit circle
 * around its small dot (20 px radius for a decoration's grips, ≥ 40 px across);
 * the resize grip's circle is pushed outwards so it never covers the glyph.
 */
const props = defineProps<{
  shape: VenueShapeRead
  width: number
  height: number
  unitsPerPixel: number
  selectedVertex?: number | null
  /** The decoration grip being dragged, for its live badge. */
  activeGrip?: PropGrip | null
}>()

const coarse = useMediaQuery('(pointer: coarse)')
const upp = computed(() => props.unitsPerPixel)
const r = computed(() => 7 * upp.value)
const hit = computed(() => (coarse.value ? 16 : 9) * upp.value)

/** Stalk length of the rotate grip (px), a bit longer for fingers. */
const STALK_PX = { fine: 20, coarse: 28 }

const prop = computed(() => {
  const s = props.shape
  if (s.kind !== 'prop') return null
  const place = propPlacement(s, props.width, props.height)
  const centre = { x: place.x, y: place.y }
  // Same ring as the shape layer's selection ring.
  const ring = propRingRadius(place.radiusUnits, upp.value)
  const stalk = (coarse.value ? STALK_PX.coarse : STALK_PX.fine) * upp.value
  const hit = (coarse.value ? 20 : 11) * upp.value
  // The resize grip's hit circle is kept off the glyph (see `resizeHit`).
  const grips = propGrips(centre, place.rotation, ring, stalk, place.radiusUnits, hit)
  return {
    centre,
    rotation: place.rotation,
    ...grips,
    hit,
    cursor: resizeCursor(grips.resizeAngle),
  }
})

/** The live value of the grip being dragged, on the far side of the glyph. */
const badge = computed(() => {
  const p = prop.value
  const grip = props.activeGrip
  if (!p || !grip) return null
  const text =
    grip === 'rotate'
      ? `${Math.round(p.rotation)}°`
      : `${Math.round((props.shape.scale ?? DEFAULT_PROP_SCALE) * 100)} %`
  const away = (grip === 'rotate' ? p.rotation : p.resizeAngle) + 180
  const at = pointAtAngle(p.centre, away, p.ring + 18 * upp.value)
  const w = (text.length * 6.5 + 12) * upp.value
  const h = 18 * upp.value
  return { text, x: at.x, y: at.y, w, h }
})

const u = (p: readonly number[]) => ({ x: p[0]! * props.width, y: p[1]! * props.height })

const resize = computed(() =>
  props.shape.kind === 'rect'
    ? RECT_HANDLES.map((handle) => ({ handle, ...u(rectHandlePoint(props.shape.points, handle)) }))
    : [],
)

const isLine = computed(() => props.shape.kind === 'polygon' || props.shape.kind === 'path')
const vertices = computed(() => (isLine.value ? props.shape.points.map(u) : []))
const inserts = computed(() =>
  isLine.value ? edgeMidpoints(props.shape.points, props.shape.kind === 'polygon').map(u) : [],
)

const label = computed(() => {
  const s = props.shape
  if (s.kind === 'label' || s.kind === 'prop' || !s.label?.trim()) return null
  const a = labelAnchor(s, props.width, props.height)
  // Just below the caption, so the grip never hides the words.
  const { fontUnits } = labelLayout(s, props.width, props.height, upp.value)
  const at = u([a.x, a.y])
  return { x: at.x, y: at.y + fontUnits * 0.6 + 9 * upp.value }
})

const CURSORS: Record<string, string> = {
  nw: 'nwse-resize',
  se: 'nwse-resize',
  ne: 'nesw-resize',
  sw: 'nesw-resize',
  n: 'ns-resize',
  s: 'ns-resize',
  e: 'ew-resize',
  w: 'ew-resize',
}
</script>

<template>
  <g class="venue-edit-handles" data-testid="edit-handles">
    <g
      v-for="h in resize"
      :key="h.handle"
      :data-handle="`resize:${h.handle}`"
      :data-testid="`handle-resize-${h.handle}`"
      :style="{ cursor: CURSORS[h.handle] }"
    >
      <circle :cx="h.x" :cy="h.y" :r="hit" fill="transparent" />
      <rect
        :x="h.x - r / 2"
        :y="h.y - r / 2"
        :width="r"
        :height="r"
        class="fill-card stroke-map-select"
        :stroke-width="1.5 * upp"
      />
    </g>

    <g
      v-for="(m, i) in inserts"
      :key="`insert-${i}`"
      :data-handle="`insert:${i}`"
      :data-testid="`handle-insert-${i}`"
      class="cursor-copy"
    >
      <circle :cx="m.x" :cy="m.y" :r="hit * 0.8" fill="transparent" />
      <circle
        :cx="m.x"
        :cy="m.y"
        :r="r * 0.55"
        class="fill-map-select/80 stroke-card"
        :stroke-width="1 * upp"
      />
      <path
        :d="`M ${m.x - r * 0.3} ${m.y} H ${m.x + r * 0.3} M ${m.x} ${m.y - r * 0.3} V ${m.y + r * 0.3}`"
        class="stroke-card"
        :stroke-width="1.25 * upp"
      />
    </g>

    <g
      v-for="(v, i) in vertices"
      :key="`vertex-${i}`"
      :data-handle="`vertex:${i}`"
      :data-testid="`handle-vertex-${i}`"
      :data-selected="selectedVertex === i ? 'true' : undefined"
      class="cursor-move"
    >
      <circle :cx="v.x" :cy="v.y" :r="hit" fill="transparent" />
      <circle
        :cx="v.x"
        :cy="v.y"
        :r="r * 0.7"
        :class="
          selectedVertex === i ? 'fill-map-select stroke-card' : 'fill-card stroke-map-select'
        "
        :stroke-width="1.5 * upp"
      />
    </g>

    <template v-if="prop">
      <line
        :x1="prop.stalk.x"
        :y1="prop.stalk.y"
        :x2="prop.rotate.x"
        :y2="prop.rotate.y"
        class="stroke-map-select"
        :stroke-width="1.5 * upp"
        pointer-events="none"
      />
      <g
        data-handle="rotate"
        data-testid="handle-rotate"
        :data-active="activeGrip === 'rotate' ? 'true' : undefined"
        :class="activeGrip === 'rotate' ? 'cursor-grabbing' : 'cursor-grab'"
      >
        <circle :cx="prop.rotate.x" :cy="prop.rotate.y" :r="prop.hit" fill="transparent" />
        <circle
          :cx="prop.rotate.x"
          :cy="prop.rotate.y"
          :r="6 * upp"
          :class="
            activeGrip === 'rotate' ? 'fill-map-select stroke-card' : 'fill-card stroke-map-select'
          "
          :stroke-width="1.5 * upp"
        />
      </g>
      <g
        data-handle="scale"
        data-testid="handle-scale"
        :data-active="activeGrip === 'scale' ? 'true' : undefined"
        :style="{ cursor: prop.cursor }"
      >
        <circle
          :cx="prop.resizeHit.x"
          :cy="prop.resizeHit.y"
          :r="prop.hit"
          fill="transparent"
        />
        <rect
          :x="prop.resize.x - r / 2"
          :y="prop.resize.y - r / 2"
          :width="r"
          :height="r"
          :transform="`rotate(${prop.rotation} ${prop.resize.x} ${prop.resize.y})`"
          :class="
            activeGrip === 'scale' ? 'fill-map-select stroke-card' : 'fill-card stroke-map-select'
          "
          :stroke-width="1.5 * upp"
        />
      </g>
      <g v-if="badge" pointer-events="none" data-testid="grip-badge">
        <rect
          :x="badge.x - badge.w / 2"
          :y="badge.y - badge.h / 2"
          :width="badge.w"
          :height="badge.h"
          :rx="badge.h / 2"
          class="fill-map-select"
        />
        <text
          :x="badge.x"
          :y="badge.y"
          :font-size="11 * upp"
          text-anchor="middle"
          dominant-baseline="central"
          class="fill-card font-semibold tabular-nums select-none"
        >
          {{ badge.text }}
        </text>
      </g>
    </template>

    <g v-if="label" data-handle="label" data-testid="handle-label" class="cursor-move">
      <circle :cx="label.x" :cy="label.y" :r="hit" fill="transparent" />
      <rect
        :x="label.x - 7 * upp"
        :y="label.y - 7 * upp"
        :width="14 * upp"
        :height="14 * upp"
        :rx="3 * upp"
        class="fill-card stroke-map-select"
        :stroke-width="1.25 * upp"
      />
      <text
        :x="label.x"
        :y="label.y"
        :font-size="10 * upp"
        text-anchor="middle"
        dominant-baseline="central"
        class="fill-map-select font-semibold select-none"
      >
        T
      </text>
    </g>
  </g>
</template>
