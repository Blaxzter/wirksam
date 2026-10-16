<script setup lang="ts">
import { type FunctionalComponent, computed, h } from 'vue'

import { useI18n } from 'vue-i18n'

import VenuePropGlyph from '@/components/venue-map/VenuePropGlyph.vue'
import {
  type PropPlacement,
  postsAlong,
  postsPath,
  propLabelKey,
  propPlacement,
  sortProps,
} from '@/lib/venue-decor'
import {
  type RenderShape,
  isProp,
  labelLayout,
  shapeKindLabelKey,
  shapeStyleClass,
  shapeStyleLabelKey,
  toPlanUnits,
} from '@/lib/venue-shapes'

/**
 * The drawn part of a venue plan: rooms, areas, paths, decoration and captions.
 *
 * A `<g>` meant for an `<svg>` whose user space is plan units (`0 0 W H`).
 * Three layers, in this order: the ground shapes (in `sort_order`), the
 * decoration (props: the ground tier, then the tall tier), then every
 * caption, so a caption is never covered by a neighbouring shape or a tree;
 * whatever the parent draws after this layer (the markers) sits on top of
 * all of it. Decoration is never a place: outside the editor it takes no
 * pointer events at all.
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

type InlineStyle = Record<string, string>

/** A texture drawn over a shape's body: an extra line or a set of posts. */
type Texture =
  | { tag: 'polyline' | 'polygon'; cls: string; points: string; style: InlineStyle }
  | { tag: 'path'; cls: string; d: string }

type Drawn = {
  shape: RenderShape
  styleClass: string
  linked: boolean
  geometry: Geometry | null
  /** Inline style for the body (plan-unit widths). */
  bodyStyle?: InlineStyle
  /** A building's soft drop shadow: its translate. */
  cast?: string
  textures: Texture[]
}

type DrawnProp = {
  shape: RenderShape
  styleClass: string
  place: PropPlacement
}

function pointsAttr(points: [number, number][]): string {
  return points.map(([x, y]) => `${x},${y}`).join(' ')
}

const px = (n: number) => `${n}px`

/** A rect's or polygon's closed outline, in plan units. */
function outline(shape: RenderShape, pts: [number, number][]): [number, number][] {
  if (shape.kind !== 'rect') return pts
  const [a, b] = pts as [[number, number], [number, number]]
  return [
    [a[0], a[1]],
    [b[0], a[1]],
    [b[0], b[1]],
    [a[0], b[1]],
  ]
}

/**
 * The extras a style adds on top of the body (geometry only, so computed once
 * per shapes/size change): a building's cast shadow, a stream's ripple, a
 * hedge's leafy dots, a fence's posts.
 */
function extrasOf(
  shape: RenderShape,
  geometry: Geometry,
  W: number,
  H: number,
): Pick<Drawn, 'bodyStyle' | 'cast' | 'textures'> {
  const short = Math.min(W, H)
  const pts = toPlanUnits(shape.points, W, H)
  const textures: Texture[] = []
  if (geometry.tag === 'polyline') {
    const sw = geometry.strokeWidth
    let bodyStyle: InlineStyle = { strokeWidth: px(sw) }
    const points = geometry.attrs.points
    if (shape.style === 'water') {
      textures.push({
        tag: 'polyline',
        cls: 'vs-ripple',
        points,
        style: { strokeWidth: px(0.12 * sw), strokeDasharray: `${0.8 * sw} ${1.5 * sw}` },
      })
    } else if (shape.style === 'hedge') {
      textures.push({
        tag: 'polyline',
        cls: 'vs-hedge-dots',
        points,
        style: { strokeWidth: px(0.45 * sw), strokeDasharray: `0 ${0.6 * sw}` },
      })
    } else if (shape.style === 'fence') {
      bodyStyle = { strokeWidth: px(Math.max(0.35 * sw, 0.0015 * short)) }
      const posts = postsAlong(pts, Math.max(4 * sw, 0.012 * short))
      textures.push({ tag: 'path', cls: 'vs-fence-posts', d: postsPath(posts, 0.9 * sw) })
    }
    return { bodyStyle, textures }
  }
  if (shape.style === 'building') {
    return { cast: `translate(${0.004 * short} ${0.006 * short})`, textures }
  }
  if (shape.style === 'hedge') {
    textures.push({
      tag: 'polygon',
      cls: 'vs-hedge-dots',
      points: pointsAttr(outline(shape, pts)),
      style: { strokeWidth: px(0.01 * short), strokeDasharray: `0 ${0.014 * short}` },
    })
  } else if (shape.style === 'fence') {
    const posts = postsAlong(outline(shape, pts), 0.03 * short, { closed: true })
    textures.push({ tag: 'path', cls: 'vs-fence-posts', d: postsPath(posts, 0.007 * short) })
    return { bodyStyle: { strokeWidth: px(0.003 * short) }, textures }
  }
  return { textures }
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
  props.shapes
    .filter((shape) => !isProp(shape))
    .map((shape) => {
      const geometry = geometryOf(shape, props.width, props.height)
      return {
        shape,
        styleClass: shapeStyleClass(shape.style),
        linked: !!shape.location_id && (shape.kind === 'rect' || shape.kind === 'polygon'),
        geometry,
        ...(geometry ? extrasOf(shape, geometry, props.width, props.height) : { textures: [] }),
      }
    }),
)

/** Decoration in drawing order, its transforms precomputed (no per-frame work). */
const drawnProps = computed<DrawnProp[]>(() =>
  sortProps(props.shapes.filter(isProp)).map((shape) => ({
    shape,
    styleClass: shapeStyleClass(shape.style),
    place: propPlacement(shape, props.width, props.height),
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
  for (const d of [...drawn.value, ...drawnProps.value]) {
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
      // A prop's caption sits on the ground below it, like a free caption.
      kindLabel: d.shape.kind === 'label' || d.shape.kind === 'prop',
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
  if (isProp(shape)) {
    const label = (shape.label ?? '').trim()
    return `${t(shapeKindLabelKey('prop'))}: ${label || t(propLabelKey(shape.prop ?? ''))}`
  }
  const style = t(shapeStyleLabelKey(shape.style))
  const label = (shape.label ?? '').trim()
  const place = shape.location_id ? props.locationNames[shape.location_id] : undefined
  return `${style}: ${label || place || t(shapeKindLabelKey(shape.kind))}`
}

function onClick(d: Drawn, event: MouseEvent) {
  if (!isTappable(d)) return
  emit('select-shape', d.shape, event)
}

function onKeydown(d: { shape: RenderShape }, event: KeyboardEvent) {
  if (props.interactive !== 'all') return
  if (event.key !== 'Enter' && event.key !== ' ') return
  event.preventDefault()
  emit('select-shape', d.shape, event)
}

function onPropClick(d: DrawnProp, event: MouseEvent) {
  if (props.interactive !== 'all') return
  emit('select-shape', d.shape, event)
}

function onPointerdown(d: { shape: RenderShape }, event: PointerEvent) {
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
const Geom: FunctionalComponent<{
  geometry: Geometry
  cls: string
  inline?: InlineStyle
  transform?: string
}> = (p) =>
  h(p.geometry.tag, {
    ...p.geometry.attrs,
    class: p.cls,
    style: p.inline,
    transform: p.transform,
  })
Geom.props = ['geometry', 'cls', 'inline', 'transform']

/** A texture over a body; its widths are plan units, set inline. */
const TextureEl: FunctionalComponent<{ texture: Texture }> = ({ texture }) =>
  texture.tag === 'path'
    ? h('path', { class: texture.cls, d: texture.d })
    : h(texture.tag, { class: texture.cls, points: texture.points, style: texture.style })
TextureEl.props = ['texture']
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
          <Geom v-if="d.cast" :geometry="d.geometry" cls="vs-cast" :transform="d.cast" />
          <Geom :geometry="d.geometry" cls="vs-body" :inline="d.bodyStyle" />
          <TextureEl v-for="(tx, i) in d.textures" :key="i" :texture="tx" />
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
    <g data-layer="props" :pointer-events="interactive === 'all' ? undefined : 'none'">
      <g
        v-for="d in drawnProps"
        :key="d.shape.id"
        class="venue-shape venue-prop-shape"
        :class="d.styleClass"
        :data-shape-id="d.shape.id"
        :data-testid="`venue-shape-${d.shape.id}`"
        data-kind="prop"
        :data-prop="d.shape.prop"
        :data-rotation="d.place.rotation"
        :data-scale="d.shape.scale ?? 1"
        :data-selected="selectedShapes.has(d.shape.id) ? 'true' : undefined"
        :role="interactive === 'all' ? 'button' : undefined"
        :tabindex="interactive === 'all' ? 0 : undefined"
        :aria-label="interactive === 'all' ? accessibleName(d.shape) : undefined"
        :aria-pressed="interactive === 'all' ? selectedShapes.has(d.shape.id) : undefined"
        :aria-hidden="interactive === 'all' ? undefined : 'true'"
        @click="onPropClick(d, $event)"
        @keydown="onKeydown(d, $event)"
        @pointerdown="onPointerdown(d, $event)"
      >
        <VenuePropGlyph
          :prop="d.shape.prop ?? ''"
          :transform="d.place.body"
          :shadow-transform="d.place.shadow"
        />
        <template v-if="interactive === 'all'">
          <circle
            class="vs-prop-hit"
            :cx="d.place.x"
            :cy="d.place.y"
            :r="Math.max(d.place.radiusUnits, 10 * unitsPerPixel)"
          />
          <template v-if="selectedShapes.has(d.shape.id)">
            <circle
              class="vs-sel-outer"
              :cx="d.place.x"
              :cy="d.place.y"
              :r="d.place.radiusUnits + 4 * unitsPerPixel"
            />
            <circle
              class="vs-sel-inner"
              :cx="d.place.x"
              :cy="d.place.y"
              :r="d.place.radiusUnits + 4 * unitsPerPixel"
            />
          </template>
        </template>
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
