<script setup lang="ts">
import { type FunctionalComponent, computed, h } from 'vue'

import { useI18n } from 'vue-i18n'

import {
  type RenderShape,
  labelLayout,
  shapeKindLabelKey,
  shapeStyleClass,
  shapeStyleLabelKey,
  toPlanUnits,
} from '@/lib/venue-shapes'

/**
 * The drawn part of a venue plan: rooms, areas, paths and captions.
 *
 * A `<g>` meant for an `<svg>` whose user space is plan units (`0 0 W H`).
 * Shapes are drawn first and every caption after them, so a caption is never
 * covered by a neighbouring shape; whatever the parent draws after this layer
 * (the markers) sits on top of both.
 *
 * Colours come from the theme (`.vs-<style>` in `index.css`), never from the
 * data, so the drawing follows light and dark mode.
 *
 * `interactive`:
 * - `'none'`: purely decorative (mini-map, print);
 * - `'linked'`: shapes linked to a place can be tapped. They are hidden from
 *   assistive tech and not focusable, because every linked area also has a
 *   pill, which is the keyboard route;
 * - `'all'`: every shape is a focusable button (the editor).
 */
const props = withDefaults(
  defineProps<{
    shapes: ReadonlyArray<RenderShape>
    /** The plan size in plan units. */
    width: number
    height: number
    unitsPerPixel: number
    interactive?: 'none' | 'linked' | 'all'
    /** Shapes linked to this place get the strong highlight. */
    selectedLocationId?: string | null
    /** Shapes linked to these places get a dashed highlight ("my shifts"). */
    highlightLocationIds?: ReadonlyArray<string>
    /** The editor's selection. */
    selectedShapeIds?: ReadonlyArray<string>
    /** Place names by id, for accessible names in `'all'` mode. */
    locationNames?: Readonly<Record<string, string>>
    showLabels?: boolean
    minLabelPx?: number
  }>(),
  {
    interactive: 'none',
    selectedLocationId: null,
    highlightLocationIds: () => [],
    selectedShapeIds: () => [],
    locationNames: () => ({}),
    showLabels: true,
    minLabelPx: 11,
  },
)

const emit = defineEmits<{
  'select-shape': [shape: RenderShape, event: MouseEvent | KeyboardEvent]
  'shape-pointerdown': [shape: RenderShape, event: PointerEvent]
}>()

const { t } = useI18n()

type Geometry =
  | { tag: 'rect'; attrs: { x: number; y: number; width: number; height: number; rx: number } }
  | { tag: 'polygon'; attrs: { points: string } }
  | { tag: 'polyline'; attrs: { points: string }; strokeWidth: number }

type Drawn = {
  shape: RenderShape
  styleClass: string
  linked: boolean
  geometry: Geometry | null
}

function pointsAttr(points: [number, number][]): string {
  return points.map(([x, y]) => `${x},${y}`).join(' ')
}

/** Geometry depends on the shapes and the plan size only, never on the zoom. */
function geometryOf(shape: RenderShape, W: number, H: number): Geometry | null {
  const pts = toPlanUnits(shape.points, W, H)
  const short = Math.min(W, H)
  if (shape.kind === 'rect') {
    const [a, b] = pts
    if (!a || !b) return null
    const x = Math.min(a[0], b[0])
    const y = Math.min(a[1], b[1])
    const w = Math.abs(b[0] - a[0])
    const hgt = Math.abs(b[1] - a[1])
    const square = shape.style === 'wall' || shape.style === 'path'
    const rx = square ? 0 : Math.min(0.006 * short, w / 4, hgt / 4)
    return { tag: 'rect', attrs: { x, y, width: w, height: hgt, rx } }
  }
  if (shape.kind === 'polygon') return { tag: 'polygon', attrs: { points: pointsAttr(pts) } }
  if (shape.kind === 'path') {
    const sw = (shape.stroke_width ?? 0.02) * short
    return { tag: 'polyline', attrs: { points: pointsAttr(pts) }, strokeWidth: sw }
  }
  return null
}

const drawn = computed<Drawn[]>(() =>
  props.shapes.map((shape) => ({
    shape,
    styleClass: shapeStyleClass(shape.style),
    linked: !!shape.location_id && (shape.kind === 'rect' || shape.kind === 'polygon'),
    geometry: geometryOf(shape, props.width, props.height),
  })),
)

/** The captions, recomputed on zoom; the geometry above is not. */
const labels = computed(() => {
  if (!props.showLabels) return []
  const out: {
    id: string
    text: string
    styleClass: string
    kindLabel: boolean
    x: number
    y: number
    fontUnits: number
  }[] = []
  for (const d of drawn.value) {
    const text = (d.shape.label ?? '').trim()
    if (!text) continue
    const layout = labelLayout(d.shape, props.width, props.height, props.unitsPerPixel, {
      minPx: props.minLabelPx,
    })
    if (!layout.visible) continue
    out.push({
      id: d.shape.id,
      text,
      styleClass: d.styleClass,
      kindLabel: d.shape.kind === 'label',
      x: layout.x,
      y: layout.y,
      fontUnits: layout.fontUnits,
    })
  }
  return out
})

const highlighted = computed(() => new Set(props.highlightLocationIds))
const selectedShapes = computed(() => new Set(props.selectedShapeIds))

function isSelectedLocation(d: Drawn): boolean {
  return d.linked && !!props.selectedLocationId && d.shape.location_id === props.selectedLocationId
}

function isHighlighted(d: Drawn): boolean {
  return d.linked && highlighted.value.has(d.shape.location_id!)
}

/** Whether a shape takes pointer events in the current mode. */
function isTappable(d: Drawn): boolean {
  if (props.interactive === 'all') return true
  return props.interactive === 'linked' && d.linked
}

function accessibleName(shape: RenderShape): string {
  const style = t(shapeStyleLabelKey(shape.style))
  const label = (shape.label ?? '').trim()
  const place = shape.location_id ? props.locationNames[shape.location_id] : undefined
  return `${style}: ${label || place || t(shapeKindLabelKey(shape.kind))}`
}

function onClick(d: Drawn, event: MouseEvent) {
  if (!isTappable(d)) return
  emit('select-shape', d.shape, event)
}

function onKeydown(d: Drawn, event: KeyboardEvent) {
  if (props.interactive !== 'all') return
  if (event.key !== 'Enter' && event.key !== ' ') return
  event.preventDefault()
  emit('select-shape', d.shape, event)
}

function onPointerdown(d: Drawn, event: PointerEvent) {
  if (props.interactive !== 'all') return
  emit('shape-pointerdown', d.shape, event)
}

/**
 * One geometry element with a class; used for the body and its overlays.
 *
 * A path's body gets its width inline: it is in plan units, and a stylesheet
 * rule would beat a presentation attribute. Its overlays keep the screen-px
 * widths their classes set.
 */
const Geom: FunctionalComponent<{ geometry: Geometry; cls: string }> = (p) => {
  const g = p.geometry
  const style =
    g.tag === 'polyline' && p.cls === 'vs-body' ? { strokeWidth: `${g.strokeWidth}px` } : undefined
  return h(g.tag, { ...g.attrs, class: p.cls, style })
}
Geom.props = ['geometry', 'cls']
</script>

<template>
  <g class="venue-shape-layer" :pointer-events="interactive === 'none' ? 'none' : undefined">
    <g data-layer="shapes">
      <g
        v-for="d in drawn"
        :key="d.shape.id"
        class="venue-shape"
        :class="[
          d.styleClass,
          {
            'vs-tappable': isTappable(d),
            'vs-label-kind': d.shape.kind === 'label',
          },
        ]"
        :data-shape-id="d.shape.id"
        :data-testid="`venue-shape-${d.shape.id}`"
        :data-kind="d.shape.kind"
        :data-linked="d.linked ? 'true' : 'false'"
        :data-selected-location="isSelectedLocation(d) ? 'true' : undefined"
        :data-highlighted="isHighlighted(d) ? 'true' : undefined"
        :data-selected="selectedShapes.has(d.shape.id) ? 'true' : undefined"
        :pointer-events="isTappable(d) ? 'visiblePainted' : 'none'"
        :role="interactive === 'all' ? 'button' : undefined"
        :tabindex="interactive === 'all' ? 0 : undefined"
        :aria-label="interactive === 'all' ? accessibleName(d.shape) : undefined"
        :aria-pressed="interactive === 'all' ? selectedShapes.has(d.shape.id) : undefined"
        :aria-hidden="interactive === 'all' ? undefined : 'true'"
        @click="onClick(d, $event)"
        @keydown="onKeydown(d, $event)"
        @pointerdown="onPointerdown(d, $event)"
      >
        <template v-if="d.geometry">
          <Geom :geometry="d.geometry" cls="vs-body" />
          <Geom v-if="isTappable(d) && d.linked" :geometry="d.geometry" cls="vs-hover" />
          <Geom v-if="isHighlighted(d)" :geometry="d.geometry" cls="vs-hl-mine" />
          <Geom v-if="isSelectedLocation(d)" :geometry="d.geometry" cls="vs-hl-selected" />
          <template v-if="selectedShapes.has(d.shape.id)">
            <Geom :geometry="d.geometry" cls="vs-sel-outer" />
            <Geom :geometry="d.geometry" cls="vs-sel-inner" />
          </template>
        </template>
        <!-- A text-only shape still needs something to hit in the editor. -->
        <circle
          v-else-if="interactive === 'all' && d.shape.points[0]"
          class="vs-label-hit"
          :cx="d.shape.points[0][0]! * width"
          :cy="d.shape.points[0][1]! * height"
          :r="10 * unitsPerPixel"
        />
      </g>
    </g>
    <g data-layer="shape-labels" pointer-events="none" aria-hidden="true">
      <text
        v-for="l in labels"
        :key="l.id"
        class="venue-shape-label"
        :class="[l.styleClass, { 'vs-label-kind': l.kindLabel }]"
        :data-testid="`venue-shape-label-${l.id}`"
        :x="l.x"
        :y="l.y"
        :font-size="l.fontUnits"
        :stroke-width="3 * unitsPerPixel"
        text-anchor="middle"
        dominant-baseline="central"
        paint-order="stroke"
        stroke-linejoin="round"
      >
        {{ l.text }}
      </text>
    </g>
  </g>
</template>
