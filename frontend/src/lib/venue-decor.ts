import type { VenueShapeRead } from '@/client/types.gen'

/**
 * Decoration ("Deko") on venue maps: trees, benches, tents and friends.
 *
 * A prop is a venue shape of kind `prop`: one normalised point plus a prop
 * type, a rotation and a scale. It is never a place, never linked and never
 * tappable outside the editor.
 *
 * Every glyph is geometry in a local frame of 48 units (±24), drawn from a few
 * primitives: an optional shadow, a base and a lighter highlight, no outlines.
 * Colours are not here: each part names a *paint*, which maps to a
 * `.vp-<paint>` class in `index.css`, so decor follows light, dark and print.
 *
 * One light comes from the top-left, so every shadow falls down-right. The
 * offset is applied in world space before the rotation: turning a bench does
 * not turn the sun.
 */

export type PropType = NonNullable<VenueShapeRead['prop']>

/** The 14 prop types, in the backend's order (`PROP_TYPES`). */
export const PROP_TYPES: readonly PropType[] = [
  'tree',
  'conifer',
  'bush',
  'flowers',
  'plant',
  'bench',
  'picnic_table',
  'round_table',
  'bin',
  'bike_rack',
  'sign',
  'parasol',
  'tent',
  'lamp',
]

export type PropTier = 'ground' | 'tall'
export type PropGroup = 'nature' | 'furniture' | 'event'

export type PropMeta = {
  group: PropGroup
  tier: PropTier
  /** Share of the plan's shorter side that the 48-unit glyph frame spans at scale 1. */
  size: number
  /** Radius of the glyph in local units (for hit area, selection ring, bounds, caption). */
  radius: number
  /** Whether new ones get a random rotation in the editor (round, natural things). */
  randomRotation: boolean
}

function meta(
  group: PropGroup,
  tier: PropTier,
  size: number,
  radius: number,
  randomRotation: boolean,
): PropMeta {
  return { group, tier, size, radius, randomRotation }
}

export const PROP_META: Readonly<Record<PropType, PropMeta>> = {
  tree: meta('nature', 'tall', 0.055, 24, true),
  conifer: meta('nature', 'tall', 0.05, 23, true),
  bush: meta('nature', 'tall', 0.032, 18, true),
  flowers: meta('nature', 'ground', 0.03, 18, true),
  plant: meta('nature', 'ground', 0.028, 16, true),
  bench: meta('furniture', 'ground', 0.03, 23, false),
  picnic_table: meta('furniture', 'ground', 0.042, 25, false),
  round_table: meta('furniture', 'ground', 0.03, 21, true),
  bin: meta('furniture', 'ground', 0.014, 9, false),
  bike_rack: meta('furniture', 'ground', 0.045, 23, false),
  sign: meta('furniture', 'ground', 0.028, 16, false),
  parasol: meta('event', 'tall', 0.04, 22, true),
  tent: meta('event', 'tall', 0.07, 31, false),
  lamp: meta('event', 'tall', 0.024, 11, false),
}

/** The props of each group, in palette order. */
export const PROP_GROUPS: Readonly<Record<PropGroup, readonly PropType[]>> = {
  nature: PROP_TYPES.filter((p) => PROP_META[p].group === 'nature'),
  furniture: PROP_TYPES.filter((p) => PROP_META[p].group === 'furniture'),
  event: PROP_TYPES.filter((p) => PROP_META[p].group === 'event'),
}

export const PROP_SCALE_RANGE: readonly [number, number] = [0.25, 4]
export const DEFAULT_PROP_SCALE = 1
export const ROTATION_STEP = 15
/** Light from the top-left: shadow offset in local units, applied in world space before rotation. */
export const SHADOW_OFFSET: readonly [number, number] = [2.5, 3.5]

/** The size and radius used for a prop type the client does not know. */
const FALLBACK_SIZE = 0.03
const FALLBACK_RADIUS = 10
/** Local units the glyph frame spans. */
const FRAME = 48

export type PropPaint =
  | 'shadow'
  | 'leaf'
  | 'leaf-hi'
  | 'conifer'
  | 'conifer-hi'
  | 'bloom'
  | 'bloom-2'
  | 'wood'
  | 'wood-dk'
  | 'fabric'
  | 'fabric-shade'
  | 'accent'
  | 'metal'
  | 'stone'
  | 'lamp'
  | 'glow'
  | 'rib'
  | 'line-wood'
  | 'line-metal'
  | 'line-light'

/** Paints that stroke (fill none); every other paint fills. */
export const LINE_PAINTS: ReadonlySet<PropPaint> = new Set<PropPaint>([
  'rib',
  'line-wood',
  'line-metal',
  'line-light',
])

export type GlyphPart =
  | { el: 'circle'; paint: PropPaint; cx?: number; cy?: number; r: number }
  | { el: 'ellipse'; paint: PropPaint; cx?: number; cy?: number; rx: number; ry: number }
  | {
      el: 'rect'
      paint: PropPaint
      x: number
      y: number
      width: number
      height: number
      rx?: number
      rotate?: number
    }
  | { el: 'path'; paint: PropPaint; d: string; rotate?: number; strokeWidth?: number }

export type PropGlyph = {
  shadow: readonly GlyphPart[]
  body: readonly GlyphPart[]
  radius: number
}

// ---------------------------------------------------------------------------
// Glyph geometry
// ---------------------------------------------------------------------------

function circle(paint: PropPaint, r: number, cx = 0, cy = 0): GlyphPart {
  return cx || cy ? { el: 'circle', paint, cx, cy, r } : { el: 'circle', paint, r }
}

function rect(
  paint: PropPaint,
  x: number,
  y: number,
  width: number,
  height: number,
  rx?: number,
  rotate?: number,
): GlyphPart {
  const part: GlyphPart = { el: 'rect', paint, x, y, width, height }
  if (rx) part.rx = rx
  if (rotate) part.rotate = rotate
  return part
}

function path(paint: PropPaint, d: string, opts: { rotate?: number; strokeWidth?: number } = {}): GlyphPart {
  const part: GlyphPart = { el: 'path', paint, d }
  if (opts.rotate) part.rotate = opts.rotate
  if (opts.strokeWidth) part.strokeWidth = opts.strokeWidth
  return part
}

/** The same part turned `count` times about the origin, starting at `start`. */
function ring(count: number, step: number, start: number, make: (rotate: number) => GlyphPart): GlyphPart[] {
  return Array.from({ length: count }, (_, i) => make(start + i * step))
}

const ARC_QUARTER = 'M0 0L0 -22A22 22 0 0 1 15.56 -15.56Z'
const LEAF = 'M0 -1C4 -5 4 -10 0 -14C-4 -10 -4 -5 0 -1Z'

const GLYPHS: Readonly<Record<PropType, Omit<PropGlyph, 'radius'>>> = {
  tree: {
    shadow: [circle('shadow', 22)],
    body: [
      circle('leaf', 21),
      circle('leaf', 13, -10, 4),
      circle('leaf', 13, 10, 5),
      circle('leaf', 13, 1, -11),
      circle('leaf-hi', 9, -5, -7),
      circle('leaf-hi', 4.5, 5, -14),
    ],
  },
  conifer: {
    shadow: [circle('shadow', 19)],
    body: [
      ...ring(6, 60, 0, (r) => path('conifer', 'M0 -23L8 3H-8Z', { rotate: r })),
      ...ring(6, 60, 30, (r) => path('conifer-hi', 'M0 -13L4.5 1.5H-4.5Z', { rotate: r })),
      circle('conifer-hi', 4),
    ],
  },
  bush: {
    shadow: [{ el: 'ellipse', paint: 'shadow', rx: 18, ry: 12 }],
    body: [
      circle('leaf', 10, -8, 2),
      circle('leaf', 9, 8, 3),
      circle('leaf', 10, 0, -5),
      circle('leaf-hi', 5, -2, -7),
    ],
  },
  flowers: {
    shadow: [],
    body: [
      { el: 'ellipse', paint: 'leaf-hi', rx: 18, ry: 12 },
      circle('bloom', 3.5, -10, -2),
      circle('bloom', 3.5, 1, 5),
      circle('bloom', 3.5, 9, -4),
      circle('bloom-2', 3.5, -3, -6),
      circle('bloom-2', 3.5, 11, 4),
      circle('bloom-2', 3.5, -8, 6),
    ],
  },
  plant: {
    shadow: [circle('shadow', 15)],
    body: [
      circle('stone', 15),
      circle('wood-dk', 12),
      ...ring(5, 72, 0, (r) => path('leaf', LEAF, { rotate: r })),
      circle('leaf-hi', 2.5),
    ],
  },
  bench: {
    shadow: [rect('shadow', -22, -9, 44, 17, 3)],
    body: [
      rect('wood', -22, -4, 44, 12, 3),
      rect('wood-dk', -22, -9, 44, 5, 2),
      path('line-wood', 'M-20 0H20M-20 4H20', { strokeWidth: 0.9 }),
    ],
  },
  picnic_table: {
    shadow: [rect('shadow', -24, -14, 48, 28, 3)],
    body: [
      rect('wood-dk', -24, -14, 48, 6, 2),
      rect('wood-dk', -24, 8, 48, 6, 2),
      rect('wood', -24, -5, 48, 10, 2),
      path('line-wood', 'M-22 0H22', { strokeWidth: 0.9 }),
    ],
  },
  round_table: {
    shadow: [circle('shadow', 14)],
    body: [...ring(4, 90, 0, (r) => rect('wood-dk', -6, -21, 12, 7, 2.5, r)), circle('wood', 13)],
  },
  bin: {
    shadow: [circle('shadow', 9)],
    body: [
      circle('metal', 9),
      circle('stone', 6.5),
      path('line-metal', 'M-4 0H4', { strokeWidth: 1.6 }),
    ],
  },
  bike_rack: {
    shadow: [],
    body: [
      path('line-metal', 'M-22 0H22', { strokeWidth: 2 }),
      path('line-metal', 'M-17 -8V8M-8.5 -8V8M0 -8V8M8.5 -8V8M17 -8V8', { strokeWidth: 2.6 }),
    ],
  },
  sign: {
    shadow: [rect('shadow', -12, -14, 24, 16, 2.5)],
    body: [
      path('line-wood', 'M0 2V14', { strokeWidth: 3.5 }),
      rect('wood', -12, -16, 24, 16, 2.5),
      path('line-light', 'M-7 -11H7M-7 -6H3', { strokeWidth: 2 }),
    ],
  },
  parasol: {
    shadow: [circle('shadow', 22)],
    body: [
      circle('fabric', 22),
      ...ring(4, 90, 0, (r) => path('accent', ARC_QUARTER, { rotate: r })),
      path(
        'rib',
        'M0 -22V22M-22 0H22M-15.56 -15.56L15.56 15.56M15.56 -15.56L-15.56 15.56',
        { strokeWidth: 0.8 },
      ),
      circle('wood-dk', 2.5),
    ],
  },
  tent: {
    shadow: [rect('shadow', -22, -22, 44, 44, 2)],
    body: [
      rect('fabric', -22, -22, 44, 44, 2),
      path('fabric-shade', 'M22 -22L0 0L22 22Z'),
      path('fabric-shade', 'M-22 22L0 0L22 22Z'),
      path('rib', 'M-22 -22L22 22M22 -22L-22 22', { strokeWidth: 0.8 }),
      circle('accent', 2.5),
    ],
  },
  lamp: {
    shadow: [],
    body: [circle('glow', 11), circle('lamp', 5)],
  },
}

/** What an unknown prop type is drawn as: a small stone with a dot. */
export const FALLBACK_GLYPH: PropGlyph = {
  shadow: [],
  body: [circle('stone', 10), circle('metal', 3.5)],
  radius: FALLBACK_RADIUS,
}

export function isPropType(value: unknown): value is PropType {
  return typeof value === 'string' && Object.prototype.hasOwnProperty.call(PROP_META, value)
}

/** A prop's glyph; an unknown or missing type gets {@link FALLBACK_GLYPH} (never throws). */
export function propGlyph(prop: string | null | undefined): PropGlyph {
  if (!isPropType(prop)) return FALLBACK_GLYPH
  return { ...GLYPHS[prop], radius: PROP_META[prop].radius }
}

/** The class a paint is drawn with (`.vp-<paint>` in `index.css`). */
export function propPaintClass(paint: PropPaint): string {
  return `vp-${paint}`
}

/** The i18n key naming a prop type (`venueMap.props.*`). */
export function propLabelKey(prop: string): string {
  return `venueMap.props.${prop}`
}

/** Degrees into `[0, 360)`, rounded to 0.1 like the backend; 360 becomes 0. */
export function normaliseRotation(deg: number): number {
  if (!Number.isFinite(deg)) return 0
  const r = Math.round((((deg % 360) + 360) % 360) * 10) / 10
  return r >= 360 ? 0 : r
}

export function clampPropScale(s: number): number {
  if (!Number.isFinite(s)) return DEFAULT_PROP_SCALE
  return Math.min(PROP_SCALE_RANGE[1], Math.max(PROP_SCALE_RANGE[0], s))
}

/** Plan units per local unit for a prop on a W×H plan. */
export function propUnit(
  prop: string,
  scale: number | null | undefined,
  W: number,
  H: number,
): number {
  const size = isPropType(prop) ? PROP_META[prop].size : FALLBACK_SIZE
  return (size * Math.min(W, H) * (scale ?? DEFAULT_PROP_SCALE)) / FRAME
}

export type PropPlacement = {
  x: number
  y: number
  /** Plan units per local unit. */
  k: number
  rotation: number
  /** `translate(x y) rotate(r) scale(k)` (rotate omitted when 0). */
  body: string
  /** The same, moved by the shadow offset in world space. */
  shadow: string
  /** The glyph radius in plan units. */
  radiusUnits: number
}

/** Rounded for short, stable attribute strings. */
function num(n: number): number {
  return Math.round(n * 10000) / 10000
}

function transform(x: number, y: number, rotation: number, k: number): string {
  const rot = rotation ? ` rotate(${num(rotation)})` : ''
  return `translate(${num(x)} ${num(y)})${rot} scale(${num(k)})`
}

/** Where and how a prop is drawn, in plan units. */
export function propPlacement(
  shape: Pick<VenueShapeRead, 'points' | 'prop' | 'rotation' | 'scale'>,
  W: number,
  H: number,
): PropPlacement {
  const p = shape.points[0]
  const x = (p?.[0] ?? 0) * W
  const y = (p?.[1] ?? 0) * H
  const prop = shape.prop ?? ''
  const k = propUnit(prop, shape.scale, W, H)
  const rotation = normaliseRotation(shape.rotation ?? 0)
  const radius = propGlyph(prop).radius
  return {
    x,
    y,
    k,
    rotation,
    body: transform(x, y, rotation, k),
    shadow: transform(x + SHADOW_OFFSET[0] * k, y + SHADOW_OFFSET[1] * k, rotation, k),
    radiusUnits: radius * k,
  }
}

function tierRank(prop: string | null | undefined): number {
  return isPropType(prop) && PROP_META[prop].tier === 'tall' ? 1 : 0
}

/** Props in drawing order: ground tier, then tall; sort_order, then id within a tier. */
export function sortProps<T extends { prop?: string | null; sort_order: number; id: string }>(
  props: readonly T[],
): T[] {
  return [...props].sort(
    (a, b) =>
      tierRank(a.prop) - tierRank(b.prop) ||
      a.sort_order - b.sort_order ||
      (a.id < b.id ? -1 : a.id > b.id ? 1 : 0),
  )
}

// ---------------------------------------------------------------------------
// Line textures (pure, plan units)
// ---------------------------------------------------------------------------

export type Post = { x: number; y: number; angle: number }

const MAX_POSTS = 200

/**
 * Posts spaced evenly by length along a polyline (plan units): `n =
 * max(1, round(len / spacing))` gaps, both ends included. A closed outline
 * includes its closing edge and has no duplicate post at the seam. `angle` is
 * the direction of the edge the post sits on, in degrees. At most `max`
 * (default 200) posts.
 */
export function postsAlong(
  points: readonly (readonly [number, number])[],
  spacing: number,
  opts: { closed?: boolean; max?: number } = {},
): Post[] {
  if (points.length === 0) return []
  const closed = Boolean(opts.closed) && points.length > 2
  const max = Math.max(1, Math.floor(opts.max ?? MAX_POSTS))
  const pts = closed ? [...points, points[0]!] : [...points]
  const segs: { ax: number; ay: number; dx: number; dy: number; len: number; angle: number }[] = []
  let total = 0
  for (let i = 0; i < pts.length - 1; i++) {
    const [ax, ay] = pts[i]!
    const [bx, by] = pts[i + 1]!
    const dx = bx - ax
    const dy = by - ay
    const len = Math.hypot(dx, dy)
    if (len <= 0) continue
    segs.push({ ax, ay, dx, dy, len, angle: (Math.atan2(dy, dx) * 180) / Math.PI })
    total += len
  }
  if (!(total > 0) || segs.length === 0) {
    const [x, y] = points[0]!
    return [{ x, y, angle: 0 }]
  }
  let gaps = Math.max(1, Math.round(total / (spacing > 0 ? spacing : total)))
  gaps = Math.min(gaps, closed ? max : max - 1 || 1)
  const count = closed ? gaps : gaps + 1
  const out: Post[] = []
  let seg = 0
  let before = 0
  for (let i = 0; i < Math.min(count, max); i++) {
    const at = (total * i) / gaps
    while (seg < segs.length - 1 && before + segs[seg]!.len < at) {
      before += segs[seg]!.len
      seg++
    }
    const s = segs[seg]!
    const t = Math.min(1, Math.max(0, (at - before) / s.len))
    out.push({ x: num(s.ax + s.dx * t), y: num(s.ay + s.dy * t), angle: num(s.angle) })
  }
  return out
}

/** One `d` with a square of side `side` per post, turned to the post's angle. */
export function postsPath(posts: readonly Post[], side: number): string {
  const h = side / 2
  return posts
    .map(({ x, y, angle }) => {
      const a = (angle * Math.PI) / 180
      const c = Math.cos(a)
      const s = Math.sin(a)
      const corner = (u: number, v: number) => `${num(x + u * c - v * s)} ${num(y + u * s + v * c)}`
      return `M${corner(-h, -h)}L${corner(h, -h)}L${corner(h, h)}L${corner(-h, h)}Z`
    })
    .join('')
}

type LinePresetKey = 'hedge' | 'fence' | 'water' | 'path'

/** The style and width (share of the shorter side) a decor line starts with. */
export const LINE_PRESETS: Readonly<
  Record<LinePresetKey, { style: LinePresetKey; strokeWidth: number }>
> = {
  hedge: { style: 'hedge', strokeWidth: 0.016 },
  fence: { style: 'fence', strokeWidth: 0.008 },
  water: { style: 'water', strokeWidth: 0.03 },
  path: { style: 'path', strokeWidth: 0.03 },
}
