<script setup lang="ts">
import { computed } from 'vue'

import { useMediaQuery } from '@vueuse/core'

import type { VenueShapeRead } from '@/client/types.gen'
import { RECT_HANDLES, edgeMidpoints, rectHandlePoint } from '@/lib/venue-shape-edit'
import { labelAnchor, labelLayout } from '@/lib/venue-shapes'

/**
 * The grips of the selected shape, drawn in plan units on top of everything:
 *
 * - a rect: eight resize handles (corners and edge midpoints);
 * - a polygon or path: one handle per vertex, plus a small "+" on every edge
 *   that inserts a vertex there when pressed;
 * - a decoration (prop): nothing — the shape layer draws its selection ring,
 *   and it is moved by dragging the glyph itself;
 * - any other shape with a caption except a text: a "T" handle that moves the
 *   caption (`label_x`/`label_y`); it sits just below the caption, and the
 *   caption follows the pointer's movement.
 *
 * The handles only *mark* where a press should go: each carries a
 * `data-handle` attribute (`resize:nw`, `vertex:2`, `insert:0`, `label`) that
 * the editor reads from the event target. On a coarse pointer each gets an
 * invisible 16 px hit circle around its 7 px dot.
 */
const props = defineProps<{
  shape: VenueShapeRead
  width: number
  height: number
  unitsPerPixel: number
  selectedVertex?: number | null
}>()

const coarse = useMediaQuery('(pointer: coarse)')
const upp = computed(() => props.unitsPerPixel)
const r = computed(() => 7 * upp.value)
const hit = computed(() => (coarse.value ? 16 : 9) * upp.value)

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
