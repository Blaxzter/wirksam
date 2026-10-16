import { describe, expect, it } from 'vitest'

import type { VenueShapeRead } from '@/client/types.gen'
import {
  MIN_POINTS,
  PROP_STYLE,
  type Pt,
  RECT_HANDLES,
  type ShapeOp,
  applyOps,
  axisLock,
  clampPt,
  constrainAngle,
  dedupePoints,
  diffShape,
  duplicateShape,
  edgeMidpoints,
  gridStep,
  hitEdge,
  insertVertex,
  invertOps,
  materialiseOps,
  moveShape,
  moveVertex,
  newShapeId,
  nextSortOrder,
  normaliseRect,
  pointsBounds,
  rectCorners,
  rectFromDrag,
  rectHandlePoint,
  rectIsBigEnough,
  removeVertex,
  reorderOps,
  resizeRect,
  round5,
  roundPoints,
  shapeToCreate,
  shapeVertices,
  snapPoint,
  sortByOrder,
} from '@/lib/venue-shape-edit'

function shape(overrides: Partial<VenueShapeRead> = {}): VenueShapeRead {
  return {
    id: 's1',
    plan_id: 'p1',
    kind: 'rect',
    style: 'room',
    points: [
      [0.1, 0.1],
      [0.3, 0.2],
    ],
    label: null,
    label_size: 'md',
    label_x: null,
    label_y: null,
    stroke_width: null,
    location_id: null,
    sort_order: 0,
    ...overrides,
  }
}

const poly = (overrides: Partial<VenueShapeRead> = {}) =>
  shape({
    id: 'poly',
    kind: 'polygon',
    style: 'area',
    points: [
      [0.1, 0.1],
      [0.5, 0.1],
      [0.5, 0.5],
    ],
    ...overrides,
  })

const path = (overrides: Partial<VenueShapeRead> = {}) =>
  shape({
    id: 'path',
    kind: 'path',
    style: 'path',
    points: [
      [0.1, 0.1],
      [0.5, 0.1],
    ],
    stroke_width: 0.02,
    ...overrides,
  })

describe('basics', () => {
  it('rounds, clamps and sorts', () => {
    expect(round5(0.123456789)).toBe(0.12346)
    expect(clampPt([-1, 2])).toEqual([0, 1])
    expect(clampPt([])).toEqual([0, 0])
    expect(roundPoints([[0.1234567, 0.7654321], []])).toEqual([
      [0.12346, 0.76543],
      [0, 0],
    ])
    expect(
      normaliseRect([
        [0.5, 0.1],
        [0.2, 0.4],
      ]),
    ).toEqual([
      [0.2, 0.1],
      [0.5, 0.4],
    ])
    // A single point is a zero-size rect, no points the origin.
    expect(normaliseRect([[0.3, 0.3]])).toEqual([
      [0.3, 0.3],
      [0.3, 0.3],
    ])
    expect(normaliseRect([])).toEqual([
      [0, 0],
      [0, 0],
    ])
    expect(pointsBounds(poly().points)).toEqual({ x0: 0.1, y0: 0.1, x1: 0.5, y1: 0.5 })
  })

  it('lists the snap vertices of each kind', () => {
    expect(rectCorners(shape().points)).toEqual([
      [0.1, 0.1],
      [0.3, 0.1],
      [0.3, 0.2],
      [0.1, 0.2],
    ])
    expect(shapeVertices(shape())).toHaveLength(4)
    expect(shapeVertices(poly())).toEqual(poly().points)
  })

  it('sorts by z order and finds the next one', () => {
    const a = shape({ id: 'a', sort_order: 2 })
    const b = shape({ id: 'b', sort_order: 0 })
    expect(sortByOrder([a, b]).map((s) => s.id)).toEqual(['b', 'a'])
    expect(nextSortOrder([a, b])).toBe(3)
    expect(nextSortOrder([])).toBe(0)
  })

  it('makes ids', () => {
    expect(newShapeId()).toMatch(/^[0-9a-f-]{36}$/)
  })
})

describe('snapping', () => {
  it('uses 1% of the shorter side as grid step', () => {
    expect(gridStep(1600, 1000)).toEqual({ gx: 10 / 1600, gy: 0.01 })
    expect(gridStep(1000, 1600)).toEqual({ gx: 0.01, gy: 10 / 1600 })
    expect(gridStep(0, 0)).toEqual({ gx: 0.01, gy: 0.01 })
  })

  const base = { W: 1000, H: 1000, upp: 1 }

  it('prefers a vertex within the radius over the grid', () => {
    const grid = gridStep(1000, 1000)
    const vertices: Pt[] = [
      [0.1234, 0.1234],
      [0.126, 0.126],
    ]
    const res = snapPoint([0.125, 0.125], { ...base, grid, vertices })
    expect(res.snappedTo).toBe('vertex')
    // The nearer of the two.
    expect(res.point).toEqual([0.126, 0.126])
  })

  it('falls back to the grid outside the radius', () => {
    const res = snapPoint([0.1234, 0.5678], {
      ...base,
      grid: { gx: 0.01, gy: 0.01 },
      vertices: [[0.9, 0.9]],
    })
    expect(res).toEqual({ point: [0.12, 0.57], snappedTo: 'grid' })
  })

  it('measures the radius in screen pixels', () => {
    // 8 px at 2 units per px is 16 units = 0.016 of a 1000-unit plan.
    expect(snapPoint([0.5, 0.5], { ...base, upp: 2, vertices: [[0.515, 0.5]] }).snappedTo).toBe(
      'vertex',
    )
    expect(snapPoint([0.5, 0.5], { ...base, upp: 1, vertices: [[0.515, 0.5]] }).snappedTo).toBe(
      null,
    )
    expect(
      snapPoint([0.5, 0.5], { ...base, radiusPx: 20, vertices: [[0.515, 0.5]] }).snappedTo,
    ).toBe('vertex')
  })

  it('does nothing without grid and vertices (Alt)', () => {
    expect(snapPoint([0.1234, 0.5], base)).toEqual({ point: [0.1234, 0.5], snappedTo: null })
    expect(snapPoint([0.1234, 0.5], { ...base, grid: { gx: 0, gy: 0 } }).snappedTo).toBe(null)
  })

  it('constrains segments to 45° steps on the real plan', () => {
    // Plan 2:1. A normalised (0.1, 0.18) is (200, 180) units: nearly 45°.
    const end = constrainAngle([0, 0], [0.1, 0.18], 2000, 1000)
    expect(end[0] * 2000).toBeCloseTo(end[1] * 1000)
    // Nearly horizontal → horizontal.
    const flat = constrainAngle([0.5, 0.5], [0.8, 0.51], 1000, 1000)
    expect(flat[1]).toBeCloseTo(0.5)
    expect(flat[0]).toBeCloseTo(0.8, 2)
    // Zero length stays.
    expect(constrainAngle([0.5, 0.5], [0.5, 0.5], 1, 1)).toEqual([0.5, 0.5])
  })

  it('locks a move to its main axis', () => {
    expect(axisLock(0.1, 0.05, 1, 1)).toEqual([0.1, 0])
    expect(axisLock(0.1, 0.15, 1, 1)).toEqual([0, 0.15])
    // Measured in plan units: 0.1 of 1000 is less than 0.06 of 2000.
    expect(axisLock(0.1, 0.06, 1000, 2000)).toEqual([0, 0.06])
  })
})

describe('rects', () => {
  it('spans a drag in any direction', () => {
    expect(rectFromDrag([0.5, 0.5], [0.2, 0.3])).toEqual([
      [0.2, 0.3],
      [0.5, 0.5],
    ])
  })

  it('makes a square in plan units with Shift', () => {
    const r = rectFromDrag([0.5, 0.5], [0.6, 0.55], { square: true, W: 2000, H: 1000 })
    // 0.1·2000 = 200 units wide → 0.2 of the height.
    expect(r[1][0]).toBeCloseTo(0.6)
    expect(r[1][1]).toBeCloseTo(0.7)
    const up = rectFromDrag([0.5, 0.5], [0.4, 0.3], { square: true })
    expect(up[0][0]).toBeCloseTo(0.3)
    expect(up[0][1]).toBeCloseTo(0.3)
    // Clipped at the plan's edge.
    expect(rectFromDrag([0.9, 0.5], [1, 0.1], { square: true })[0][1]).toBeCloseTo(0.1)
  })

  it('knows when a rect is big enough', () => {
    expect(rectIsBigEnough(shape().points)).toBe(true)
    expect(
      rectIsBigEnough([
        [0.1, 0.1],
        [0.101, 0.3],
      ]),
    ).toBe(false)
  })

  it('resizes from every handle and keeps the minimum size', () => {
    const r = shape({
      points: [
        [0.2, 0.2],
        [0.4, 0.4],
      ],
    })
    const expected: Record<string, number[][]> = {
      nw: [
        [0.1, 0.1],
        [0.4, 0.4],
      ],
      n: [
        [0.2, 0.1],
        [0.4, 0.4],
      ],
      ne: [
        [0.2, 0.1],
        [0.5, 0.4],
      ],
      e: [
        [0.2, 0.2],
        [0.5, 0.4],
      ],
      se: [
        [0.2, 0.2],
        [0.5, 0.5],
      ],
      s: [
        [0.2, 0.2],
        [0.4, 0.5],
      ],
      sw: [
        [0.1, 0.2],
        [0.4, 0.5],
      ],
      w: [
        [0.1, 0.2],
        [0.4, 0.4],
      ],
    }
    for (const handle of RECT_HANDLES) {
      const target = rectHandlePoint(expected[handle]!, handle)
      expect(resizeRect(r, handle, target).points, handle).toEqual(expected[handle])
    }
    // Dragged past the opposite side: stops at the minimum.
    expect(resizeRect(r, 'e', [0.1, 0.3]).points).toEqual([
      [0.2, 0.2],
      [0.202, 0.4],
    ])
    expect(resizeRect(r, 'n', [0.3, 0.9]).points[0]![1]).toBeCloseTo(0.398)
    // Not a rect: unchanged.
    const p = poly()
    expect(resizeRect(p, 'e', [0.9, 0.9])).toBe(p)
  })

  it('places handles on corners and edge midpoints', () => {
    const pts = [
      [0.2, 0.2],
      [0.4, 0.6],
    ]
    expect(rectHandlePoint(pts, 'n')).toEqual([0.30000000000000004, 0.2])
    expect(rectHandlePoint(pts, 'se')).toEqual([0.4, 0.6])
    expect(rectHandlePoint(pts, 'w')).toEqual([0.2, 0.4])
  })
})

describe('moving and vertices', () => {
  it('moves a shape and clamps it to the plan, label anchor included', () => {
    const s = shape({ label_x: 0.2, label_y: 0.15 })
    const moved = moveShape(s, 0.1, 0.05)
    expect(moved.points).toEqual([
      [0.2, 0.15],
      [0.4, 0.25],
    ])
    expect([moved.label_x, moved.label_y]).toEqual([0.3, 0.2])
    // Too far left/up: stops at the edge.
    const clamped = moveShape(s, -1, -1)
    expect(clamped.points[0]).toEqual([0, 0])
    // No anchor: none appears.
    expect(moveShape(shape(), 0.1, 0).label_x).toBeNull()
    // Input untouched.
    expect(s.points[0]).toEqual([0.1, 0.1])
  })

  it('moves a vertex, re-sorting a rect', () => {
    const p = moveVertex(poly(), 1, [0.6, 0.2])
    expect(p.points[1]).toEqual([0.6, 0.2])
    const r = moveVertex(shape(), 0, [0.5, 0.5])
    expect(r.points).toEqual([
      [0.3, 0.2],
      [0.5, 0.5],
    ])
    const s = poly()
    expect(moveVertex(s, 7, [0, 0])).toBe(s)
  })

  it('inserts vertices on polygons and paths only, within the limits', () => {
    const p = insertVertex(poly(), 0, [0.3, 0.05])
    expect(p.points).toHaveLength(4)
    expect(p.points[1]).toEqual([0.3, 0.05])
    expect(insertVertex(path(), 0, [0.3, 0.1]).points).toHaveLength(3)
    const r = shape()
    expect(insertVertex(r, 0, [0.2, 0.1])).toBe(r)
    const full = poly({ points: Array.from({ length: 500 }, (_, i) => [i / 500, 0.5]) })
    expect(insertVertex(full, 0, [0, 0])).toBe(full)
    const s = poly()
    expect(insertVertex(s, 3, [0, 0])).toBe(s)
    expect(insertVertex(s, -1, [0, 0])).toBe(s)
  })

  it('removes vertices but never below the minimum', () => {
    const square = poly({
      points: [
        [0, 0],
        [1, 0],
        [1, 1],
        [0, 1],
      ],
    })
    expect(removeVertex(square, 0).points).toHaveLength(3)
    const tri = poly()
    expect(removeVertex(tri, 0)).toBe(tri)
    const line = path()
    expect(removeVertex(line, 0)).toBe(line)
    const r = shape()
    expect(removeVertex(r, 0)).toBe(r)
    expect(removeVertex(square, 9)).toBe(square)
  })

  it('finds the nearest edge within the tolerance', () => {
    const pts = poly().points
    const hit = hitEdge(pts, [0.3, 0.11], 0.02, true)
    expect(hit?.index).toBe(0)
    expect(hit?.point[0]).toBeCloseTo(0.3)
    expect(hit?.point[1]).toBeCloseTo(0.1)
    // The closing edge (2 → 0) only for closed shapes.
    expect(hitEdge(pts, [0.3, 0.31], 0.02, true)?.index).toBe(2)
    expect(hitEdge(pts, [0.3, 0.31], 0.02, false)).toBeNull()
    // In plan units on a wide plan.
    expect(hitEdge(pts, [0.3, 0.12], 15, true, 1000, 1000)).toBeNull()
    expect(hitEdge(pts, [0.3, 0.12], 15, true, 1000, 500)?.index).toBe(0)
    // A zero-length edge.
    expect(
      hitEdge(
        [
          [0.5, 0.5],
          [0.5, 0.5],
        ],
        [0.5, 0.5],
        0.01,
        false,
      )?.distance,
    ).toBe(0)
  })

  it('lists edge midpoints', () => {
    expect(edgeMidpoints(path().points, false)).toEqual([[0.3, 0.1]])
    expect(edgeMidpoints(poly().points, true)).toHaveLength(3)
  })

  it('duplicates under a new id on top', () => {
    const copy = duplicateShape(shape(), 'copy', { dx: 0.05, dy: 0.05 }, 9)
    expect(copy.id).toBe('copy')
    expect(copy.sort_order).toBe(9)
    expect(copy.points[0]).toEqual([0.15, 0.15])
  })

  it('drops coinciding consecutive points', () => {
    expect(
      dedupePoints([
        [0.1, 0.1],
        [0.1, 0.1],
        [0.2, 0.2],
        [0.1, 0.1],
      ]),
    ).toHaveLength(3)
  })
})

describe('ops', () => {
  it('diffs only what changed', () => {
    const a = shape()
    expect(diffShape(a, { ...a })).toBeNull()
    expect(diffShape(a, { ...a, label: undefined })).toBeNull()
    expect(diffShape(a, { ...a, style: 'stage', label: 'Bühne' })).toEqual({
      style: 'stage',
      label: 'Bühne',
    })
    expect(diffShape({ ...a, location_id: 'l1' }, { ...a, location_id: undefined })).toEqual({
      location_id: null,
    })
    expect(diffShape(a, moveShape(a, 0.1, 0))).toEqual({
      points: [
        [0.2, 0.1],
        [0.4, 0.2],
      ],
    })
  })

  it('turns a shape into a full create body', () => {
    expect(shapeToCreate(path({ label: 'x' }))).toEqual({
      id: 'path',
      kind: 'path',
      style: 'path',
      points: [
        [0.1, 0.1],
        [0.5, 0.1],
      ],
      label: 'x',
      label_size: 'md',
      label_x: null,
      label_y: null,
      stroke_width: 0.02,
      location_id: null,
      sort_order: 0,
    })
    const bare = shapeToCreate({
      ...shape(),
      label: undefined,
      label_x: undefined,
      label_y: undefined,
      stroke_width: undefined,
      location_id: undefined,
    })
    expect(bare.label).toBeNull()
    expect(bare.location_id).toBeNull()
  })

  it('applies creates, updates and deletes like the server', () => {
    const base = [shape({ id: 'a', sort_order: 0 }), shape({ id: 'b', sort_order: 1 })]
    const out = applyOps(
      base,
      [
        {
          op: 'create',
          shape: {
            id: 'c',
            kind: 'rect',
            style: 'stage',
            points: [
              [0.5, 0.5],
              [0.4, 0.4],
            ],
            label: '  Bühne ',
          },
        },
        {
          op: 'create',
          shape: {
            id: 'd',
            kind: 'path',
            style: 'path',
            points: [
              [0, 0],
              [1, 1],
            ],
          },
        },
        {
          op: 'update',
          id: 'a',
          patch: {
            style: null,
            points: null,
            label_size: null,
            sort_order: null,
            label: ' Hall ',
            location_id: 'l1',
          },
        },
        { op: 'update', id: 'b', patch: { sort_order: 9, label: '   ' } },
        { op: 'update', id: 'zzz', patch: { label: 'x' } },
        { op: 'delete', id: 'nope' },
      ],
      'p1',
    )
    expect(out.map((s) => s.id)).toEqual(['a', 'c', 'd', 'b'])
    const c = out.find((s) => s.id === 'c')!
    expect(c.points).toEqual([
      [0.4, 0.4],
      [0.5, 0.5],
    ])
    expect(c.label).toBe('Bühne')
    expect(c.sort_order).toBe(2)
    expect(c.plan_id).toBe('p1')
    expect(c.stroke_width).toBeNull()
    expect(out.find((s) => s.id === 'd')!.stroke_width).toBe(0.02)
    const a = out.find((s) => s.id === 'a')!
    expect(a.style).toBe('room')
    expect(a.label).toBe('Hall')
    expect(a.location_id).toBe('l1')
    expect(out.find((s) => s.id === 'b')!.label).toBeNull()

    expect(applyOps(out, [{ op: 'delete', id: 'c' }]).map((s) => s.id)).toEqual(['a', 'd', 'b'])
    // Plan id from the list when none is given; nothing at all on an empty list.
    const fromList = applyOps(base, [
      { op: 'create', shape: { kind: 'label', style: 'room', points: [[0.5, 0.5]], label: 'x' } },
    ])
    expect(fromList.at(-1)!.plan_id).toBe('p1')
    expect(fromList.at(-1)!.id).toBe('')
    expect(
      applyOps(
        [],
        [{ op: 'create', shape: { kind: 'label', style: 'room', points: [[0, 0]], label: null } }],
      )[0]!.plan_id,
    ).toBe('')
  })

  it('materialises ids and z order of creates', () => {
    let n = 0
    const ops = materialiseOps(
      [shape({ sort_order: 4 })],
      [
        { op: 'create', shape: { kind: 'label', style: 'room', points: [[0, 0]], label: 'a' } },
        { op: 'create', shape: { kind: 'label', style: 'room', points: [[0, 0]], label: 'b' } },
        {
          op: 'create',
          shape: {
            id: 'x',
            sort_order: 1,
            kind: 'label',
            style: 'room',
            points: [[0, 0]],
            label: 'c',
          },
        },
        { op: 'delete', id: 's1' },
      ],
      () => `id${++n}`,
    )
    expect(
      ops.map((op) => (op.op === 'create' ? [op.shape.id, op.shape.sort_order] : op.op)),
    ).toEqual([['id1', 5], ['id2', 6], ['x', 1], 'delete'])
  })

  it('inverts ops so that applying both is the identity', () => {
    const a = shape({ id: 'a', sort_order: 0, label: 'Hall', location_id: 'l1' })
    const b = poly({ id: 'b', sort_order: 1 })
    const before = [a, b]
    const ops: ShapeOp[] = [
      {
        op: 'create',
        shape: {
          id: 'c',
          kind: 'label',
          style: 'room',
          points: [[0.5, 0.5]],
          label: 'Hi',
          sort_order: 2,
        },
      },
      { op: 'update', id: 'c', patch: { label: 'Hello' } },
      { op: 'update', id: 'a', patch: { style: 'stage', location_id: null, label: 'Stage' } },
      { op: 'update', id: 'a', patch: { label: 'Big stage' } },
      { op: 'delete', id: 'b' },
      { op: 'update', id: 'gone', patch: { label: 'x' } },
      { op: 'delete', id: 'gone' },
    ]
    const after = applyOps(before, ops, 'p1')
    expect(after.map((s) => s.id)).toEqual(['a', 'c'])
    const inverse = invertOps(ops, new Map(before.map((s) => [s.id, s])))
    expect(inverse[0]).toEqual({ op: 'create', shape: shapeToCreate(b) })
    const restored = applyOps(after, inverse, 'p1')
    expect(restored).toEqual(before)
    // …and inverting the inverse redoes it.
    const redo = invertOps(inverse, new Map(after.map((s) => [s.id, s])))
    expect(applyOps(restored, redo, 'p1')).toEqual(after)
  })

  it('swaps z order with the neighbour', () => {
    const list = [
      shape({ id: 'a', sort_order: 0 }),
      shape({ id: 'b', sort_order: 1 }),
      shape({ id: 'c', sort_order: 1 }),
    ]
    expect(reorderOps(list, 'a', 1)).toEqual([
      { op: 'update', id: 'a', patch: { sort_order: 1 } },
      { op: 'update', id: 'b', patch: { sort_order: 0 } },
    ])
    // Tied with the neighbour: step past it.
    expect(reorderOps(list, 'b', 1)).toEqual([{ op: 'update', id: 'b', patch: { sort_order: 2 } }])
    expect(reorderOps(list, 'c', -1)).toEqual([{ op: 'update', id: 'c', patch: { sort_order: 0 } }])
    expect(reorderOps(list, 'c', 1)).toEqual([])
    expect(reorderOps(list, 'a', -1)).toEqual([])
    expect(reorderOps(list, 'nope', 1)).toEqual([])
  })
})

describe('decoration (prop)', () => {
  const tree = (overrides: Partial<VenueShapeRead> = {}) =>
    shape({
      kind: 'prop',
      style: 'green',
      points: [[0.5, 0.5]],
      prop: 'tree',
      rotation: 30,
      scale: 1.5,
      ...overrides,
    })

  it('has one point and is never a snap target', () => {
    expect(MIN_POINTS.prop).toBe(1)
    expect(shapeVertices(tree())).toEqual([])
  })

  it('has a family style for every type', () => {
    expect(PROP_STYLE.tree).toBe('green')
    expect(PROP_STYLE.lamp).toBe('furniture')
    expect(PROP_STYLE.tent).toBe('area')
  })

  it('moves within the plan, and a copy keeps type, turn and size', () => {
    expect(moveShape(tree(), 0.8, -0.9).points).toEqual([[1, 0]])
    expect(duplicateShape(tree(), 'c', { dx: 0.04, dy: 0.04 }, 7)).toMatchObject({
      id: 'c',
      points: [[0.54, 0.54]],
      prop: 'tree',
      rotation: 30,
      scale: 1.5,
      sort_order: 7,
    })
  })

  it('diffs and inverts type, turn and size', () => {
    const before = tree()
    const after = tree({ prop: 'conifer', rotation: 45, scale: 2 })
    expect(diffShape(before, after)).toEqual({ prop: 'conifer', rotation: 45, scale: 2 })
    expect(diffShape(before, tree())).toBeNull()
    const inverse = invertOps(
      [{ op: 'update', id: 's1', patch: { rotation: 45, scale: 2 } }],
      new Map([['s1', before]]),
    )
    expect(inverse).toEqual([{ op: 'update', id: 's1', patch: { rotation: 30, scale: 1.5 } }])
  })

  it('re-creates a deleted decoration with all its fields', () => {
    const before = tree()
    const [create] = invertOps([{ op: 'delete', id: 's1' }], new Map([['s1', before]]))
    expect(create).toEqual({ op: 'create', shape: shapeToCreate(before) })
    expect(shapeToCreate(before)).toMatchObject({ prop: 'tree', rotation: 30, scale: 1.5 })
    // Other kinds do not send the decoration fields at all.
    expect(shapeToCreate(shape())).not.toHaveProperty('prop')
    expect(applyOps([], [create!], 'p1')).toEqual([before])
  })

  it('applies creates and updates like the server', () => {
    const [created] = applyOps(
      [],
      [
        {
          op: 'create',
          shape: { id: 'n', kind: 'prop', style: 'green', points: [[0.2, 0.3]], prop: 'bush' },
        },
      ],
      'p1',
    )
    expect(created).toMatchObject({ prop: 'bush', rotation: 0, scale: 1, stroke_width: null })
    const [rect] = applyOps(
      [],
      [
        {
          op: 'create',
          shape: {
            id: 'r',
            kind: 'rect',
            style: 'room',
            points: [
              [0, 0],
              [0.1, 0.1],
            ],
          },
        },
      ],
    )
    expect(rect).not.toHaveProperty('prop')
    // An explicit null cannot clear them.
    const [updated] = applyOps(
      [created!],
      [{ op: 'update', id: 'n', patch: { prop: null, rotation: null, scale: 2 } }],
    )
    expect(updated).toMatchObject({ prop: 'bush', rotation: 0, scale: 2 })
  })
})
