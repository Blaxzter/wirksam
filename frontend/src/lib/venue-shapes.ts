import type { VenueMarkerRead, VenuePlanRead, VenueShapeRead } from '@/client/types.gen'

import { estimateTextWidth } from './venue-map'

/**
 * Drawn venue maps (#185 phase 2): the shapes a plan is made of.
 *
 * Shapes store their points in **normalised** plan coordinates (`0..1` of the
 * plan's width and height), exactly like markers, so a plan whose picture is
 * replaced keeps its drawing. The renderer works in **plan units** (`0..W`,
 * `0..H`), the effective plan size: the picture's pixel size if it has one,
 * else the blank canvas's logical size.
 *
 * Everything here is pure; `VenueShapeLayer.vue` draws with it and the editor
 * builds on it.
 */

export type ShapeKind = VenueShapeRead['kind']
export type ShapeStyle = VenueShapeRead['style']
export type LabelSize = VenueShapeRead['label_size']

/** What the renderer needs; the editor's drafts satisfy it too. */
export type RenderShape = Pick<
  VenueShapeRead,
  | 'id'
  | 'kind'
  | 'style'
  | 'points'
  | 'label'
  | 'label_size'
  | 'label_x'
  | 'label_y'
  | 'stroke_width'
  | 'location_id'
  | 'sort_order'
>

/** A normalised bounding box, sorted (`x0 <= x1`, `y0 <= y1`). */
export type Bounds = { x0: number; y0: number; x1: number; y1: number }

/** Every style, in the order the style picker lists them. */
export const SHAPE_STYLES = [
  'building',
  'room',
  'area',
  'stage',
  'furniture',
  'green',
  'water',
  'parking',
  'path',
  'wall',
] as const satisfies readonly ShapeStyle[]

export const SHAPE_KINDS = [
  'rect',
  'polygon',
  'path',
  'label',
] as const satisfies readonly ShapeKind[]

/** The kinds that can be linked to a location (they enclose an area). */
export const LINKABLE_KINDS = ['rect', 'polygon'] as const satisfies readonly ShapeKind[]

/** The style a freshly drawn shape of each kind starts with. */
export const DEFAULT_STYLE: Record<ShapeKind, ShapeStyle> = {
  rect: 'room',
  polygon: 'area',
  path: 'path',
  label: 'room',
}

/** Caption size as a share of the plan's shorter side, in plan units. */
export const LABEL_SIZE_FRACTION: Record<LabelSize, number> = {
  sm: 0.018,
  md: 0.026,
  lg: 0.04,
}

/** A path's width when none is set, as a share of the plan's shorter side. */
export const DEFAULT_STROKE_WIDTH = 0.02
export const MAX_SHAPES_PER_PLAN = 500
export const MAX_POINTS_PER_SHAPE = 500
export const MAX_LABEL_LENGTH = 120

/** A blank canvas's size when a plan somehow reports none. */
const FALLBACK_SIZE = { W: 1600, H: 1000 }

/** Screen size limits for captions (CSS px). */
const LABEL_HIDE_BELOW_PX = 4
const LABEL_MIN_PX = 11
const LABEL_MAX_PX = 32
/** How far a caption may overhang its shape (CSS px) before it is hidden. */
const LABEL_OVERHANG_PX = 8

/** Prefix of the id a virtual marker (a pill for a drawn area) carries. */
const VIRTUAL_PREFIX = 'shape:'

/** The i18n key naming a style (`venueMap.shapeStyles.*`). */
export function shapeStyleLabelKey(style: string): string {
  return `venueMap.shapeStyles.${style}`
}

/** The i18n key naming a kind (`venueMap.shapeKinds.*`). */
export function shapeKindLabelKey(kind: string): string {
  return `venueMap.shapeKinds.${kind}`
}

/**
 * Literal class names per style, so they are greppable next to the CSS in
 * `index.css` (`.vs-room { --vs-fill: … }`). Unknown styles fall back to `room`.
 */
const STYLE_CLASSES: Record<ShapeStyle, string> = {
  building: 'vs-building',
  room: 'vs-room',
  area: 'vs-area',
  stage: 'vs-stage',
  furniture: 'vs-furniture',
  green: 'vs-green',
  water: 'vs-water',
  parking: 'vs-parking',
  path: 'vs-path',
  wall: 'vs-wall',
}

export function shapeStyleClass(style: string): string {
  return STYLE_CLASSES[style as ShapeStyle] ?? STYLE_CLASSES.room
}

/** The plan's effective size in plan units (picture size, else canvas size). */
export function planSize(plan: Pick<VenuePlanRead, 'width' | 'height'>): { W: number; H: number } {
  const W = plan.width > 0 ? plan.width : 0
  const H = plan.height > 0 ? plan.height : 0
  return W && H ? { W, H } : { ...FALLBACK_SIZE }
}

/** A plan counts as a map once it has a picture or at least one shape. */
export function planHasMap(plan: Pick<VenuePlanRead, 'image_etag' | 'shapes'>): boolean {
  return Boolean(plan.image_etag) || (plan.shapes?.length ?? 0) > 0
}

/**
 * The class for a plan's drawing surface: `map-light` when it has a picture.
 *
 * Uploaded floor plans are nearly always light and cannot be recoloured, so a
 * picture plan keeps the light map tokens even in dark mode (see `index.css`).
 */
export function planSurfaceClass(plan: { image_etag?: string | null } | null | undefined): string {
  return plan?.image_etag ? 'map-light' : ''
}

/** Normalised points → plan units. */
export function toPlanUnits(
  points: readonly (readonly number[])[],
  W: number,
  H: number,
): [number, number][] {
  return points.map((p) => [p[0]! * W, p[1]! * H])
}

/** The bounding box of a list of normalised points. */
function pointsBounds(points: readonly (readonly number[])[]): Bounds {
  let x0 = Infinity
  let y0 = Infinity
  let x1 = -Infinity
  let y1 = -Infinity
  for (const p of points) {
    const x = p[0]!
    const y = p[1]!
    if (x < x0) x0 = x
    if (x > x1) x1 = x
    if (y < y0) y0 = y
    if (y > y1) y1 = y
  }
  if (x0 === Infinity) return { x0: 0, y0: 0, x1: 0, y1: 0 }
  return { x0, y0, x1, y1 }
}

/** A rect's two corner points, sorted into min/max (normalised). */
export function rectBounds(points: readonly (readonly number[])[]): Bounds {
  return pointsBounds(points)
}

/**
 * A shape's normalised bounding box. A path's box includes half its stroke
 * width; pass the plan size so that width (a share of the shorter side) is
 * converted per axis.
 */
export function shapeBounds(shape: RenderShape, W = 1, H = 1): Bounds {
  const b = pointsBounds(shape.points)
  if (shape.kind !== 'path') return b
  const half = ((shape.stroke_width ?? DEFAULT_STROKE_WIDTH) * Math.min(W, H)) / 2
  const hx = W > 0 ? half / W : 0
  const hy = H > 0 ? half / H : 0
  return { x0: b.x0 - hx, y0: b.y0 - hy, x1: b.x1 + hx, y1: b.y1 + hy }
}

function bboxCentre(points: readonly (readonly number[])[]): { x: number; y: number } {
  const b = pointsBounds(points)
  return { x: (b.x0 + b.x1) / 2, y: (b.y0 + b.y1) / 2 }
}

function polygonCentroid(points: readonly (readonly number[])[]): { x: number; y: number } {
  let twiceArea = 0
  let cx = 0
  let cy = 0
  const n = points.length
  for (let i = 0; i < n; i++) {
    const a = points[i]!
    const b = points[(i + 1) % n]!
    const x0 = a[0]!
    const y0 = a[1]!
    const x1 = b[0]!
    const y1 = b[1]!
    const cross = x0 * y1 - x1 * y0
    twiceArea += cross
    cx += (x0 + x1) * cross
    cy += (y0 + y1) * cross
  }
  if (Math.abs(twiceArea / 2) < 1e-9) return bboxCentre(points)
  return { x: cx / (3 * twiceArea), y: cy / (3 * twiceArea) }
}

function pathMidpoint(points: readonly (readonly number[])[]): { x: number; y: number } {
  const lengths: number[] = []
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i]!
    const b = points[i + 1]!
    lengths.push(Math.hypot(b[0]! - a[0]!, b[1]! - a[1]!))
  }
  const total = lengths.reduce((s, l) => s + l, 0)
  const first = points[0]!
  if (!(total > 0)) return { x: first[0]!, y: first[1]! }
  let remaining = total / 2
  for (let i = 0; i < lengths.length; i++) {
    const seg = lengths[i]!
    if (remaining <= seg && seg > 0) {
      const t = remaining / seg
      const a = points[i]!
      const b = points[i + 1]!
      const ax = a[0]!
      const ay = a[1]!
      return { x: ax + (b[0]! - ax) * t, y: ay + (b[1]! - ay) * t }
    }
    remaining -= seg
  }
  /* v8 ignore next 2 -- float rounding only */
  const last = points[points.length - 1]!
  return { x: last[0]!, y: last[1]! }
}

/**
 * Where a shape's pill or caption sits, in normalised coordinates.
 *
 * rect: centre. polygon: area centroid (bbox centre when degenerate). path:
 * halfway along its length. label: its point. Must match the backend's
 * `shape_anchor` (`app/logic/venue_shapes.py`); both are tested against
 * `backend/tests/fixtures/shape_anchor_cases.json`.
 */
export function shapeAnchor(
  kind: ShapeKind,
  points: readonly (readonly number[])[],
): { x: number; y: number } {
  if (points.length === 0) return { x: 0, y: 0 }
  if (kind === 'polygon') return polygonCentroid(points)
  if (kind === 'path') return pathMidpoint(points)
  if (kind === 'label') return { x: points[0]![0]!, y: points[0]![1]! }
  return bboxCentre(points)
}

function isLinkedArea(shape: RenderShape): boolean {
  return Boolean(shape.location_id) && (shape.kind === 'rect' || shape.kind === 'polygon')
}

/** A caption's nominal size in plan units: its share of the shorter side. */
export function labelFontUnits(
  shape: Pick<RenderShape, 'label_size'>,
  W: number,
  H: number,
): number {
  const fraction = LABEL_SIZE_FRACTION[shape.label_size] ?? LABEL_SIZE_FRACTION.md
  return fraction * Math.min(W, H)
}

/**
 * Where a shape's caption is centred (normalised).
 *
 * An explicit anchor (`label_x`/`label_y`) wins. A linked area carries its
 * pill at the centre, so its caption sits bottom-centre inside the box
 * instead; `fontUnits` (default: the nominal size) sets how far up from the
 * bottom edge. Everything else is captioned at its {@link shapeAnchor}.
 */
export function labelAnchor(
  shape: RenderShape,
  W = 1,
  H = 1,
  fontUnits = labelFontUnits(shape, W, H),
): { x: number; y: number } {
  if (shape.label_x != null && shape.label_y != null) return { x: shape.label_x, y: shape.label_y }
  if (isLinkedArea(shape)) {
    const b = pointsBounds(shape.points)
    const lift = H > 0 ? (0.6 * fontUnits) / H : 0
    return { x: (b.x0 + b.x1) / 2, y: Math.max(b.y0 + (b.y1 - b.y0) / 2, b.y1 - lift) }
  }
  return shapeAnchor(shape.kind, shape.points)
}

export type LabelLayout = {
  visible: boolean
  /** The size to draw at, in plan units (screen size × units per pixel). */
  fontUnits: number
  /** Centre of the caption, in plan units. */
  x: number
  y: number
}

/**
 * How to draw a shape's caption at the current zoom (`upp` = plan units per
 * CSS pixel).
 *
 * The caption scales with the plan, but its screen size is clamped to
 * `[minPx, maxPx]` so it stays readable zoomed out and calm zoomed in. A
 * caption that would be under 4px at its nominal size is hidden. An area's
 * caption that is wider than the area shrinks to fit, down to `minPx`; below
 * that it is hidden (it appears as you zoom in). Paths and free labels are
 * never hidden by width.
 */
export function labelLayout(
  shape: RenderShape,
  W: number,
  H: number,
  upp: number,
  opts: { minPx?: number; maxPx?: number } = {},
): LabelLayout {
  const minPx = opts.minPx ?? LABEL_MIN_PX
  const maxPx = opts.maxPx ?? LABEL_MAX_PX
  const scale = upp > 0 ? upp : 1
  const nominal = labelFontUnits(shape, W, H)
  const px = nominal / scale
  let sizePx = Math.min(maxPx, Math.max(minPx, px))
  const text = (shape.label ?? '').trim()
  let visible = text.length > 0 && px >= LABEL_HIDE_BELOW_PX
  if (visible && (shape.kind === 'rect' || shape.kind === 'polygon')) {
    const b = pointsBounds(shape.points)
    const roomPx = ((b.x1 - b.x0) * W) / scale + LABEL_OVERHANG_PX
    const widthPx = estimateTextWidth(text, sizePx)
    if (widthPx > roomPx) {
      // Shrink to fit a narrow area, but never below the readable minimum.
      const fitPx = (sizePx * roomPx) / widthPx
      if (fitPx >= minPx) sizePx = fitPx
      else visible = false
    }
  }
  const fontUnits = sizePx * scale
  const anchor = labelAnchor(shape, W, H, fontUnits)
  return { visible, fontUnits, x: anchor.x * W, y: anchor.y * H }
}

/** Shapes in drawing order: `sort_order` ascending, then id for stability. */
export function sortShapes<T extends { sort_order: number; id: string }>(
  shapes: readonly T[],
): T[] {
  return [...shapes].sort(
    (a, b) => a.sort_order - b.sort_order || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0),
  )
}

/** Whether a marker id names a virtual marker (a pill for a drawn area). */
export function isVirtualMarkerId(id: string): boolean {
  return id.startsWith(VIRTUAL_PREFIX)
}

/**
 * Pills for places drawn as areas: one per location that has a linked
 * rect/polygon on this plan but no marker there, at the anchor of its first
 * such shape (by `sort_order`). Mirrors the backend's virtual `LocationPin`.
 */
export function virtualMarkers(
  plan: Pick<VenuePlanRead, 'id' | 'markers' | 'shapes'>,
): VenueMarkerRead[] {
  const marked = new Set<string>()
  for (const m of plan.markers ?? []) if (m.location_id) marked.add(m.location_id)
  const out: VenueMarkerRead[] = []
  const seen = new Set<string>()
  for (const shape of sortShapes(plan.shapes ?? [])) {
    const loc = shape.location_id
    if (!loc || !isLinkedArea(shape) || marked.has(loc) || seen.has(loc)) continue
    seen.add(loc)
    const at = shapeAnchor(shape.kind, shape.points)
    out.push({
      id: `${VIRTUAL_PREFIX}${shape.id}`,
      plan_id: plan.id,
      kind: 'location',
      location_id: loc,
      label: null,
      x: at.x,
      y: at.y,
    })
  }
  return out
}

/** A plan's real markers followed by its virtual ones. */
export function planMarkers(
  plan: Pick<VenuePlanRead, 'id' | 'markers' | 'shapes'>,
): VenueMarkerRead[] {
  return [...(plan.markers ?? []), ...virtualMarkers(plan)]
}
