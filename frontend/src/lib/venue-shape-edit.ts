import type {
  ShapeCreateOp,
  ShapeDeleteOp,
  ShapeUpdateOp,
  VenueShapeCreate,
  VenueShapeRead,
  VenueShapeUpdate,
} from '@/client/types.gen'

/**
 * Pure geometry and edit operations for drawing on a venue plan (#185 phase 2).
 *
 * Everything here works in **normalised** plan coordinates (`0..1` of the
 * plan's width and height, like markers and like the API) unless a parameter
 * says otherwise. `W` and `H` are the plan's effective size in plan units;
 * they are only needed where a distance or an angle has to be measured on the
 * real, non-square plan.
 *
 * The edit operations return new objects and never mutate their input, so the
 * history (`useShapeHistory`) can keep every state it has seen.
 */

export type Pt = [number, number]
export type ShapeKind = VenueShapeRead['kind']
export type ShapeOp = ShapeCreateOp | ShapeUpdateOp | ShapeDeleteOp
export type RectHandle = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w'
export type Bounds = { x0: number; y0: number; x1: number; y1: number }

/** Smallest rectangle the server accepts, per axis (normalised). */
export const MIN_RECT_SIZE = 0.002
export const MAX_POINTS = 500
/** Fewest points each kind may have. */
export const MIN_POINTS: Record<ShapeKind, number> = { rect: 2, polygon: 3, path: 2, label: 1 }
/** Vertex snapping radius, CSS px. */
export const SNAP_RADIUS_PX = 8
export const RECT_HANDLES: readonly RectHandle[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w']

/** The fields an update can change; `kind`, `id` and `plan_id` never change. */
const EDITABLE_FIELDS = [
  'style',
  'points',
  'label',
  'label_size',
  'label_x',
  'label_y',
  'stroke_width',
  'location_id',
  'sort_order',
] as const satisfies readonly (keyof VenueShapeRead & keyof VenueShapeUpdate)[]

type EditableField = (typeof EDITABLE_FIELDS)[number]

const DECIMALS = 1e5

export function round5(value: number): number {
  return Math.round(value * DECIMALS) / DECIMALS
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

export function clampPt(p: readonly number[]): Pt {
  return [clamp(p[0] ?? 0, 0, 1), clamp(p[1] ?? 0, 0, 1)]
}

export function roundPoints(points: readonly (readonly number[])[]): Pt[] {
  return points.map((p) => [round5(p[0] ?? 0), round5(p[1] ?? 0)])
}

/** A rect's two corners sorted into top-left, bottom-right. */
export function normaliseRect(points: readonly (readonly number[])[]): Pt[] {
  const [a = [0, 0], b = a] = points
  return [
    [Math.min(a[0]!, b[0]!), Math.min(a[1]!, b[1]!)],
    [Math.max(a[0]!, b[0]!), Math.max(a[1]!, b[1]!)],
  ]
}

export function pointsBounds(points: readonly (readonly number[])[]): Bounds {
  const xs = points.map((p) => p[0]!)
  const ys = points.map((p) => p[1]!)
  return { x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) }
}

/** A rect's four corners, clockwise from the top left. */
export function rectCorners(points: readonly (readonly number[])[]): Pt[] {
  const [[x0, y0], [x1, y1]] = normaliseRect(points)
  return [
    [x0, y0],
    [x1, y0],
    [x1, y1],
    [x0, y1],
  ]
}

/** Every point another point may snap to: rect corners, polygon and path vertices. */
export function shapeVertices(shape: Pick<VenueShapeRead, 'kind' | 'points'>): Pt[] {
  if (shape.kind === 'rect') return rectCorners(shape.points)
  return shape.points.map((p) => [p[0]!, p[1]!])
}

// ── Snapping ──────────────────────────────────────────────────────────────

/** The grid: 1% of the plan's shorter side, as normalised steps per axis. */
export function gridStep(W: number, H: number): { gx: number; gy: number } {
  const side = Math.min(W, H)
  if (!(side > 0)) return { gx: 0.01, gy: 0.01 }
  return { gx: (0.01 * side) / W, gy: (0.01 * side) / H }
}

export type SnapOptions = {
  /** Grid step; leave it out to switch grid snapping off. */
  grid?: { gx: number; gy: number }
  /** Candidate vertices (normalised); leave out or empty for none. */
  vertices?: readonly Pt[]
  /** Plan units per CSS pixel at the current zoom. */
  upp: number
  W: number
  H: number
  radiusPx?: number
}

export type SnapResult = { point: Pt; snappedTo: 'vertex' | 'grid' | null }

/**
 * Snap a point: to the nearest vertex within `radiusPx` on screen first, else
 * to the grid. Alt (no snapping) is the caller's business — it simply passes
 * neither a grid nor vertices.
 */
export function snapPoint(p: Pt, opts: SnapOptions): SnapResult {
  const radius = (opts.radiusPx ?? SNAP_RADIUS_PX) * opts.upp
  let best: Pt | null = null
  let bestDistance = Infinity
  for (const v of opts.vertices ?? []) {
    const d = Math.hypot((v[0] - p[0]) * opts.W, (v[1] - p[1]) * opts.H)
    if (d <= radius && d < bestDistance) {
      best = v
      bestDistance = d
    }
  }
  if (best) return { point: [best[0], best[1]], snappedTo: 'vertex' }
  if (opts.grid && opts.grid.gx > 0 && opts.grid.gy > 0) {
    const { gx, gy } = opts.grid
    return {
      point: clampPt([round5(Math.round(p[0] / gx) * gx), round5(Math.round(p[1] / gy) * gy)]),
      snappedTo: 'grid',
    }
  }
  return { point: [p[0], p[1]], snappedTo: null }
}

/**
 * Shift-constrain the segment `from → to` to the nearest multiple of 45°,
 * measured on the real plan (not the normalised square). Its length is the
 * projection onto that direction, so the end stays near the pointer.
 */
export function constrainAngle(from: Pt, to: Pt, W: number, H: number): Pt {
  const dx = (to[0] - from[0]) * W
  const dy = (to[1] - from[1]) * H
  if (dx === 0 && dy === 0) return [to[0], to[1]]
  const step = Math.PI / 4
  const angle = Math.round(Math.atan2(dy, dx) / step) * step
  const ux = Math.cos(angle)
  const uy = Math.sin(angle)
  const length = dx * ux + dy * uy
  return clampPt([from[0] + (ux * length) / W, from[1] + (uy * length) / H])
}

/** Shift on a move: keep only the larger axis of the movement. */
export function axisLock(dx: number, dy: number, W: number, H: number): [number, number] {
  return Math.abs(dx * W) >= Math.abs(dy * H) ? [dx, 0] : [0, dy]
}

/**
 * The rect spanned by a drag from `a` to `b`, as sorted corners. With
 * `square` the shorter side grows to the longer one (in plan units, so it is
 * square on screen), towards the pointer, and is clipped to the plan.
 */
export function rectFromDrag(
  a: Pt,
  b: Pt,
  opts: { square?: boolean; W?: number; H?: number } = {},
): Pt[] {
  if (!opts.square) return normaliseRect([a, b])
  const W = opts.W ?? 1
  const H = opts.H ?? 1
  const side = Math.max(Math.abs(b[0] - a[0]) * W, Math.abs(b[1] - a[1]) * H)
  const sx = b[0] >= a[0] ? 1 : -1
  const sy = b[1] >= a[1] ? 1 : -1
  return normaliseRect([a, clampPt([a[0] + (sx * side) / W, a[1] + (sy * side) / H])])
}

export function rectIsBigEnough(points: readonly (readonly number[])[]): boolean {
  const [[x0, y0], [x1, y1]] = normaliseRect(points)
  return x1 - x0 >= MIN_RECT_SIZE - 1e-9 && y1 - y0 >= MIN_RECT_SIZE - 1e-9
}

// ── Editing one shape ─────────────────────────────────────────────────────

type Geometry = Pick<VenueShapeRead, 'kind' | 'points' | 'label_x' | 'label_y'>

/**
 * Move a whole shape by `(dx, dy)`, clamped so its points stay on the plan.
 * A moved label anchor travels along.
 */
export function moveShape<T extends Geometry>(shape: T, dx: number, dy: number): T {
  const b = pointsBounds(shape.points)
  const cx = clamp(dx, -b.x0, 1 - b.x1)
  const cy = clamp(dy, -b.y0, 1 - b.y1)
  const next: T = {
    ...shape,
    points: roundPoints(shape.points.map((p) => [p[0]! + cx, p[1]! + cy])),
  }
  if (shape.label_x != null && shape.label_y != null) {
    next.label_x = round5(clamp(shape.label_x + cx, 0, 1))
    next.label_y = round5(clamp(shape.label_y + cy, 0, 1))
  }
  return next
}

/** Put vertex `index` at `p`. A rect's "vertex" is one of its two stored corners. */
export function moveVertex<T extends Geometry>(shape: T, index: number, p: Pt): T {
  if (index < 0 || index >= shape.points.length) return shape
  const points = shape.points.map((q, i) => (i === index ? clampPt(p) : [q[0]!, q[1]!]))
  return { ...shape, points: roundPoints(shape.kind === 'rect' ? normaliseRect(points) : points) }
}

/** Insert `p` after vertex `edgeIndex` (on the edge to the next vertex). Polygons and paths only. */
export function insertVertex<T extends Geometry>(shape: T, edgeIndex: number, p: Pt): T {
  if (shape.kind !== 'polygon' && shape.kind !== 'path') return shape
  if (shape.points.length >= MAX_POINTS) return shape
  if (edgeIndex < 0 || edgeIndex >= shape.points.length) return shape
  const points = shape.points.map((q) => [q[0]!, q[1]!])
  points.splice(edgeIndex + 1, 0, clampPt(p))
  return { ...shape, points: roundPoints(points) }
}

/** Remove vertex `index`, unless that would leave fewer points than the kind needs. */
export function removeVertex<T extends Geometry>(shape: T, index: number): T {
  if (shape.kind !== 'polygon' && shape.kind !== 'path') return shape
  if (shape.points.length <= MIN_POINTS[shape.kind]) return shape
  if (index < 0 || index >= shape.points.length) return shape
  return { ...shape, points: shape.points.filter((_, i) => i !== index) }
}

/**
 * Drag one of a rect's eight handles to `p`. The opposite side stays put, and
 * the rect never gets smaller than the server allows: a side dragged past its
 * opposite stops there.
 */
export function resizeRect<T extends Geometry>(shape: T, handle: RectHandle, p: Pt): T {
  if (shape.kind !== 'rect') return shape
  let [[x0, y0], [x1, y1]] = normaliseRect(shape.points)
  const [px, py] = clampPt(p)
  if (handle.includes('w')) x0 = Math.min(px, x1 - MIN_RECT_SIZE)
  if (handle.includes('e')) x1 = Math.max(px, x0 + MIN_RECT_SIZE)
  if (handle.includes('n')) y0 = Math.min(py, y1 - MIN_RECT_SIZE)
  if (handle.includes('s')) y1 = Math.max(py, y0 + MIN_RECT_SIZE)
  return {
    ...shape,
    points: roundPoints([
      [x0, y0],
      [x1, y1],
    ]),
  }
}

/** Where a rect handle sits (normalised). */
export function rectHandlePoint(points: readonly (readonly number[])[], handle: RectHandle): Pt {
  const [[x0, y0], [x1, y1]] = normaliseRect(points)
  const x = handle.includes('w') ? x0 : handle.includes('e') ? x1 : (x0 + x1) / 2
  const y = handle.includes('n') ? y0 : handle.includes('s') ? y1 : (y0 + y1) / 2
  return [x, y]
}

/**
 * The edge of `points` closest to `p`, if it is within `tolUnits` plan units.
 * `index` is the edge's first vertex, `point` the nearest point on it.
 */
export function hitEdge(
  points: readonly (readonly number[])[],
  p: Pt,
  tolUnits: number,
  closed: boolean,
  W = 1,
  H = 1,
): { index: number; point: Pt; distance: number } | null {
  const n = points.length
  const edges = closed ? n : n - 1
  let best: { index: number; point: Pt; distance: number } | null = null
  for (let i = 0; i < edges; i++) {
    const a = points[i]!
    const b = points[(i + 1) % n]!
    const ax = a[0]! * W
    const ay = a[1]! * H
    const bx = b[0]! * W
    const by = b[1]! * H
    const qx = p[0] * W
    const qy = p[1] * H
    const len2 = (bx - ax) ** 2 + (by - ay) ** 2
    const t = len2 > 0 ? clamp(((qx - ax) * (bx - ax) + (qy - ay) * (by - ay)) / len2, 0, 1) : 0
    const x = ax + t * (bx - ax)
    const y = ay + t * (by - ay)
    const distance = Math.hypot(qx - x, qy - y)
    if (distance <= tolUnits && (!best || distance < best.distance)) {
      best = { index: i, point: [x / W, y / H], distance }
    }
  }
  return best
}

/** Midpoints of every edge (the editor's "+" handles). */
export function edgeMidpoints(points: readonly (readonly number[])[], closed: boolean): Pt[] {
  const n = points.length
  const edges = closed ? n : n - 1
  const out: Pt[] = []
  for (let i = 0; i < edges; i++) {
    const a = points[i]!
    const b = points[(i + 1) % n]!
    out.push([(a[0]! + b[0]!) / 2, (a[1]! + b[1]!) / 2])
  }
  return out
}

/** A copy under a new id, shifted by `offset` (clamped to the plan), on top of everything. */
export function duplicateShape<T extends Geometry & { id: string; sort_order: number }>(
  shape: T,
  newId: string,
  offset: { dx: number; dy: number },
  sortOrder: number,
): T {
  return { ...moveShape(shape, offset.dx, offset.dy), id: newId, sort_order: sortOrder }
}

/** Drop consecutive points that coincide (a double click adds the same point twice). */
export function dedupePoints(points: readonly Pt[], epsilon = 1e-6): Pt[] {
  const out: Pt[] = []
  for (const p of points) {
    const last = out[out.length - 1]
    if (last && Math.abs(last[0] - p[0]) <= epsilon && Math.abs(last[1] - p[1]) <= epsilon) {
      continue
    }
    out.push(p)
  }
  return out
}

// ── Ops ───────────────────────────────────────────────────────────────────

function sameValue(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if ((a === null || a === undefined) && (b === null || b === undefined)) return true
  return JSON.stringify(a) === JSON.stringify(b)
}

/** The patch that turns `before` into `after`, or `null` when nothing changed. */
export function diffShape(
  before: Pick<VenueShapeRead, EditableField>,
  after: Pick<VenueShapeRead, EditableField>,
): VenueShapeUpdate | null {
  const patch: Record<string, unknown> = {}
  for (const field of EDITABLE_FIELDS) {
    if (!sameValue(before[field], after[field])) patch[field] = after[field] ?? null
  }
  return Object.keys(patch).length > 0 ? (patch as VenueShapeUpdate) : null
}

/** A full create body for `shape`, keeping its id — what an undone delete sends. */
export function shapeToCreate(shape: VenueShapeRead): VenueShapeCreate {
  return {
    id: shape.id,
    kind: shape.kind,
    style: shape.style,
    points: shape.points.map((p) => [p[0]!, p[1]!] as [number, number]),
    label: shape.label ?? null,
    label_size: shape.label_size,
    label_x: shape.label_x ?? null,
    label_y: shape.label_y ?? null,
    stroke_width: shape.stroke_width ?? null,
    location_id: shape.location_id ?? null,
    sort_order: shape.sort_order,
  }
}

/** The z order for a shape put on top of `shapes`. */
export function nextSortOrder(shapes: readonly { sort_order: number }[]): number {
  return shapes.reduce((max, s) => Math.max(max, s.sort_order + 1), 0)
}

/** Sorted by z order; ties keep their current order (stable). */
export function sortByOrder<T extends { sort_order: number }>(shapes: readonly T[]): T[] {
  return [...shapes].sort((a, b) => a.sort_order - b.sort_order)
}

function readFromCreate(
  create: VenueShapeCreate,
  planId: string,
  sortOrder: number,
): VenueShapeRead {
  const points =
    create.kind === 'rect' ? normaliseRect(create.points) : create.points.map((p) => [p[0], p[1]])
  return {
    id: create.id ?? '',
    plan_id: planId,
    kind: create.kind,
    style: create.style,
    points: roundPoints(points),
    label: create.label?.trim() || null,
    label_size: create.label_size ?? 'md',
    label_x: create.label_x ?? null,
    label_y: create.label_y ?? null,
    stroke_width: create.kind === 'path' ? (create.stroke_width ?? 0.02) : null,
    location_id: create.location_id ?? null,
    sort_order: create.sort_order ?? sortOrder,
  }
}

function mergePatch(shape: VenueShapeRead, patch: VenueShapeUpdate): VenueShapeRead {
  const next = { ...shape } as Record<string, unknown>
  for (const field of EDITABLE_FIELDS) {
    if (!(field in patch)) continue
    const value = (patch as Record<string, unknown>)[field]
    // The server ignores an explicit null for these: they cannot be cleared.
    if (
      value == null &&
      (field === 'style' || field === 'points' || field === 'label_size' || field === 'sort_order')
    ) {
      continue
    }
    next[field] = value ?? null
  }
  const merged = next as VenueShapeRead
  if (merged.kind === 'rect') merged.points = normaliseRect(merged.points)
  if (typeof merged.label === 'string') merged.label = merged.label.trim() || null
  return merged
}

/**
 * Apply ops locally, the way the server will — the optimistic view. Unknown
 * ids are skipped rather than thrown on: the server is the judge, and its
 * answer replaces this anyway.
 */
export function applyOps(
  shapes: readonly VenueShapeRead[],
  ops: readonly ShapeOp[],
  planId = '',
): VenueShapeRead[] {
  let list = [...shapes]
  for (const op of ops) {
    if (op.op === 'create') {
      list.push(readFromCreate(op.shape, planId || list[0]?.plan_id || '', nextSortOrder(list)))
    } else if (op.op === 'update') {
      list = list.map((s) => (s.id === op.id ? mergePatch(s, op.patch) : s))
    } else {
      list = list.filter((s) => s.id !== op.id)
    }
  }
  return sortByOrder(list)
}

/**
 * Give every create op an id and an explicit `sort_order`, so replaying it
 * (redo) puts the shape back exactly where it was.
 */
export function materialiseOps(
  shapes: readonly VenueShapeRead[],
  ops: readonly ShapeOp[],
  newId: () => string,
): ShapeOp[] {
  let list = [...shapes]
  const out: ShapeOp[] = []
  for (const op of ops) {
    let next = op
    if (op.op === 'create' && (op.shape.id == null || op.shape.sort_order == null)) {
      next = {
        op: 'create',
        shape: {
          ...op.shape,
          id: op.shape.id ?? newId(),
          sort_order: op.shape.sort_order ?? nextSortOrder(list),
        },
      }
    }
    out.push(next)
    list = applyOps(list, [next])
  }
  return out
}

/**
 * The ops that undo `ops`, given the shapes as they were before them:
 * a create becomes a delete, a delete re-creates the shape under the same id
 * with every field, an update restores the previous values of the fields it
 * touched. Returned in reverse order. Create ops must carry their id (see
 * {@link materialiseOps}).
 */
export function invertOps(
  ops: readonly ShapeOp[],
  before: ReadonlyMap<string, VenueShapeRead>,
): ShapeOp[] {
  const state = new Map(before)
  const inverse: ShapeOp[] = []
  for (const op of ops) {
    if (op.op === 'create') {
      const id = op.shape.id!
      inverse.push({ op: 'delete', id })
      state.set(id, readFromCreate(op.shape, '', op.shape.sort_order ?? 0))
    } else if (op.op === 'delete') {
      const prior = state.get(op.id)
      if (prior) inverse.push({ op: 'create', shape: shapeToCreate(prior) })
      state.delete(op.id)
    } else {
      const prior = state.get(op.id)
      if (!prior) continue
      const restore: Record<string, unknown> = {}
      for (const field of Object.keys(op.patch) as EditableField[]) {
        if (EDITABLE_FIELDS.includes(field)) restore[field] = prior[field] ?? null
      }
      inverse.push({ op: 'update', id: op.id, patch: restore as VenueShapeUpdate })
      state.set(op.id, mergePatch(prior, op.patch))
    }
  }
  return inverse.reverse()
}

/**
 * Ops that move a shape one step up (`1`) or down (`-1`) the z order, by
 * swapping `sort_order` with its neighbour. Empty when it is already at the
 * end.
 */
export function reorderOps(
  shapes: readonly VenueShapeRead[],
  id: string,
  direction: 1 | -1,
): ShapeOp[] {
  const sorted = sortByOrder(shapes)
  const index = sorted.findIndex((s) => s.id === id)
  const other = sorted[index + direction]
  if (index < 0 || !other) return []
  const self = sorted[index]!
  if (self.sort_order === other.sort_order) {
    return [{ op: 'update', id, patch: { sort_order: other.sort_order + direction } }]
  }
  return [
    { op: 'update', id, patch: { sort_order: other.sort_order } },
    { op: 'update', id: other.id, patch: { sort_order: self.sort_order } },
  ]
}

/** A random id for a shape created here (the server honours client ids). */
export function newShapeId(): string {
  return crypto.randomUUID()
}
