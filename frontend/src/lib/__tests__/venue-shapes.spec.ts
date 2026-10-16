import { describe, expect, it } from 'vitest'

import type { VenueMarkerRead, VenueShapeRead } from '@/client/types.gen'
import { estimateTextWidth } from '@/lib/venue-map'
import {
  DEFAULT_STROKE_WIDTH,
  DEFAULT_STYLE,
  LABEL_SIZE_FRACTION,
  LABEL_STYLES,
  LINKABLE_KINDS,
  MAX_LABEL_LENGTH,
  MAX_POINTS_PER_SHAPE,
  MAX_SHAPES_PER_PLAN,
  PATH_STYLES_FIRST,
  type RenderShape,
  SHAPE_KINDS,
  SHAPE_STYLES,
  isProp,
  isVirtualMarkerId,
  labelAnchor,
  labelFontUnits,
  labelLayout,
  planHasMap,
  planMarkers,
  planSize,
  planSurfaceClass,
  rectBounds,
  shapeAnchor,
  shapeBounds,
  shapeKindLabelKey,
  shapeStyleClass,
  shapeStyleLabelKey,
  sortShapes,
  toPlanUnits,
  virtualMarkers,
} from '@/lib/venue-shapes'

// The same cases the backend's `shape_anchor` is tested against, so the pill
// the server places for a drawn area and the one the map draws agree.
import anchorCases from '../../../../backend/tests/fixtures/shape_anchor_cases.json'

function shape(overrides: Partial<RenderShape> = {}): RenderShape {
  return {
    id: 's1',
    kind: 'rect',
    style: 'room',
    points: [
      [0.1, 0.2],
      [0.5, 0.6],
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

describe('vocabulary', () => {
  it('lists every style, kind and default', () => {
    expect(SHAPE_STYLES).toHaveLength(13)
    expect(SHAPE_STYLES.slice(-3)).toEqual(['hedge', 'fence', 'sand'])
    expect(SHAPE_KINDS).toEqual(['rect', 'polygon', 'path', 'label', 'prop'])
    expect(LINKABLE_KINDS).toEqual(['rect', 'polygon'])
    expect(DEFAULT_STYLE).toEqual({
      rect: 'room',
      polygon: 'area',
      path: 'path',
      label: 'room',
      prop: 'green',
    })
    expect(LABEL_SIZE_FRACTION.sm).toBeLessThan(LABEL_SIZE_FRACTION.md)
    expect(LABEL_SIZE_FRACTION.md).toBeLessThan(LABEL_SIZE_FRACTION.lg)
    expect(DEFAULT_STROKE_WIDTH).toBe(0.02)
    expect([MAX_SHAPES_PER_PLAN, MAX_POINTS_PER_SHAPE, MAX_LABEL_LENGTH]).toEqual([500, 500, 120])
  })

  it('names styles and kinds through i18n keys and CSS classes', () => {
    expect(shapeStyleLabelKey('green')).toBe('venueMap.shapeStyles.green')
    expect(shapeKindLabelKey('path')).toBe('venueMap.shapeKinds.path')
    for (const style of SHAPE_STYLES) expect(shapeStyleClass(style)).toBe(`vs-${style}`)
    expect(shapeStyleClass('neon')).toBe('vs-room')
  })

  it('offers captions no line-only styles, and paths their line styles first', () => {
    expect(LABEL_STYLES).not.toContain('wall')
    expect(LABEL_STYLES).not.toContain('fence')
    expect(LABEL_STYLES).not.toContain('hedge')
    expect(LABEL_STYLES).toContain('sand')
    expect(LABEL_STYLES).toHaveLength(10)
    expect(PATH_STYLES_FIRST.slice(0, 5)).toEqual(['path', 'water', 'hedge', 'fence', 'wall'])
    expect([...PATH_STYLES_FIRST].sort()).toEqual([...SHAPE_STYLES].sort())
  })

  it('tells decoration apart', () => {
    expect(isProp({ kind: 'prop' })).toBe(true)
    expect(isProp({ kind: 'label' })).toBe(false)
  })
})

describe('props', () => {
  // A tree at scale 1 on a 1600×1000 plan: 0.055 · 1000 / 48 units per local
  // unit, radius 24 local units → 27.5 plan units.
  const tree = shape({
    kind: 'prop',
    style: 'green',
    prop: 'tree',
    rotation: 0,
    scale: 1,
    points: [[0.5, 0.5]],
  })

  it('anchors at its point', () => {
    expect(shapeAnchor('prop', [[0.3, 0.4]])).toEqual({ x: 0.3, y: 0.4 })
  })

  it('is bounded by its glyph radius, per axis', () => {
    const b = shapeBounds(tree, 1600, 1000)
    expect(b.x0).toBeCloseTo(0.5 - 27.5 / 1600)
    expect(b.x1).toBeCloseTo(0.5 + 27.5 / 1600)
    expect(b.y0).toBeCloseTo(0.5 - 27.5 / 1000)
    expect(b.y1).toBeCloseTo(0.5 + 27.5 / 1000)
    const doubled = shapeBounds({ ...tree, scale: 2 }, 1600, 1000)
    expect(doubled.y1).toBeCloseTo(0.5 + 55 / 1000)
    expect(shapeBounds(tree, 0, 0)).toEqual({ x0: 0.5, y0: 0.5, x1: 0.5, y1: 0.5 })
  })

  it('captions just below the glyph unless placed', () => {
    const at = labelAnchor({ ...tree, label: 'Old oak' }, 1600, 1000, 20)
    expect(at.x).toBeCloseTo(0.5)
    expect(at.y).toBeCloseTo(0.5 + (27.5 + 14) / 1000)
    expect(labelAnchor({ ...tree, label_x: 0.1, label_y: 0.2 }, 1600, 1000)).toEqual({
      x: 0.1,
      y: 0.2,
    })
    expect(labelAnchor(tree, 1600, 0, 20)).toEqual({ x: 0.5, y: 0.5 })
  })

  it('never hides a caption for want of width', () => {
    const long = { ...tree, label: 'A very long caption for a very small bin', prop: 'bin' as const }
    const layout = labelLayout(long, 1600, 1000, 1)
    expect(layout.visible).toBe(true)
    expect(layout.x).toBeCloseTo(800)
  })
})

describe('plans', () => {
  it('uses the effective size, falling back for a plan without one', () => {
    expect(planSize({ width: 1200, height: 800 })).toEqual({ W: 1200, H: 800 })
    expect(planSize({ width: 0, height: 800 })).toEqual({ W: 1600, H: 1000 })
  })

  it('counts a plan as a map once it has a picture or a shape', () => {
    expect(planHasMap({ image_etag: 'e', shapes: [] })).toBe(true)
    expect(planHasMap({ image_etag: null, shapes: [shape() as VenueShapeRead] })).toBe(true)
    expect(planHasMap({ image_etag: null, shapes: [] })).toBe(false)
    expect(planHasMap({ image_etag: null })).toBe(false)
  })

  it('keeps picture plans light', () => {
    expect(planSurfaceClass({ image_etag: 'e' })).toBe('map-light')
    expect(planSurfaceClass({ image_etag: null })).toBe('')
    expect(planSurfaceClass(null)).toBe('')
  })
})

describe('geometry', () => {
  it('converts to plan units', () => {
    expect(toPlanUnits([[0.5, 0.25]], 1000, 400)).toEqual([[500, 100]])
  })

  it('sorts rect corners', () => {
    expect(
      rectBounds([
        [0.5, 0.6],
        [0.1, 0.2],
      ]),
    ).toEqual({ x0: 0.1, y0: 0.2, x1: 0.5, y1: 0.6 })
    expect(rectBounds([])).toEqual({ x0: 0, y0: 0, x1: 0, y1: 0 })
  })

  it('widens a path by half its stroke, per axis', () => {
    const path = shape({
      kind: 'path',
      points: [
        [0.2, 0.5],
        [0.8, 0.5],
      ],
      stroke_width: 0.04,
    })
    // 0.04 × min(2000, 1000) / 2 = 20 units: 0.01 of W, 0.02 of H.
    const b = shapeBounds(path, 2000, 1000)
    expect(b.x0).toBeCloseTo(0.19)
    expect(b.x1).toBeCloseTo(0.81)
    expect(b.y0).toBeCloseTo(0.48)
    expect(b.y1).toBeCloseTo(0.52)
    // Default width, unit plan.
    expect(shapeBounds({ ...path, stroke_width: null }).y0).toBeCloseTo(0.49)
    expect(shapeBounds(path, 0, 0).x0).toBeCloseTo(0.2)
    expect(shapeBounds(shape())).toEqual({ x0: 0.1, y0: 0.2, x1: 0.5, y1: 0.6 })
  })

  it.each(anchorCases.cases)('anchor: $name', ({ kind, points, expected }) => {
    const at = shapeAnchor(kind as RenderShape['kind'], points)
    expect(at.x).toBeCloseTo(expected[0]!, 9)
    expect(at.y).toBeCloseTo(expected[1]!, 9)
  })

  it('anchors an empty shape at the origin', () => {
    expect(shapeAnchor('polygon', [])).toEqual({ x: 0, y: 0 })
  })
})

describe('labels', () => {
  it('sizes captions by the shorter side', () => {
    expect(labelFontUnits({ label_size: 'md' }, 1600, 1000)).toBeCloseTo(26)
    expect(labelFontUnits({ label_size: 'lg' }, 1000, 1600)).toBeCloseTo(40)
    expect(labelFontUnits({ label_size: 'xl' as 'md' }, 1000, 1000)).toBeCloseTo(26)
  })

  it('anchors a caption: explicit, bottom of a linked area, else the shape anchor', () => {
    expect(labelAnchor(shape({ label_x: 0.3, label_y: 0.9 }))).toEqual({ x: 0.3, y: 0.9 })
    // Only one coordinate set: ignored.
    expect(labelAnchor(shape({ label_x: 0.3 }))).toEqual({ x: 0.3, y: 0.4 })

    const linked = shape({ location_id: 'loc' })
    const at = labelAnchor(linked, 1000, 1000, 20)
    expect(at.x).toBeCloseTo(0.3)
    expect(at.y).toBeCloseTo(0.6 - 0.012)
    // A huge caption never climbs above the centre (where the pill is).
    expect(labelAnchor(linked, 1000, 1000, 10000).y).toBeCloseTo(0.4)
    expect(labelAnchor(linked, 1000, 0).y).toBeCloseTo(0.6)

    const label = shape({ kind: 'label', points: [[0.7, 0.8]] })
    expect(labelAnchor(label)).toEqual({ x: 0.7, y: 0.8 })
  })

  it('hides a caption under 4px and clamps the rest to 11..32px', () => {
    const label = shape({ kind: 'label', points: [[0.5, 0.5]], label: 'Gate' })
    // md on 1000×1000 = 26 units.
    expect(labelLayout(label, 1000, 1000, 10).visible).toBe(false) // 2.6px
    const small = labelLayout(label, 1000, 1000, 5) // 5.2px → 11px
    expect(small.visible).toBe(true)
    expect(small.fontUnits).toBeCloseTo(55)
    expect(small.x).toBe(500)
    const big = labelLayout(label, 1000, 1000, 0.1) // 260px → 32px
    expect(big.fontUnits).toBeCloseTo(3.2)
    expect(labelLayout(label, 1000, 1000, 1, { minPx: 30 }).fontUnits).toBeCloseTo(30)
    expect(labelLayout(label, 1000, 1000, 1, { maxPx: 20 }).fontUnits).toBeCloseTo(20)
    // A non-positive scale counts as 1.
    expect(labelLayout(label, 1000, 1000, 0).fontUnits).toBeCloseTo(26)
  })

  it('hides empty captions', () => {
    expect(labelLayout(shape({ label: '   ' }), 1000, 1000, 1).visible).toBe(false)
    expect(labelLayout(shape(), 1000, 1000, 1).visible).toBe(false)
  })

  it('hides an area caption wider than its area, but never a path or label', () => {
    const text = 'A rather long room name'
    const room = shape({
      label: text,
      points: [
        [0.1, 0.1],
        [0.15, 0.2],
      ],
    })
    // 50 units wide at 1px per unit; the caption is far wider.
    expect(estimateTextWidth(text, 26)).toBeGreaterThan(58)
    expect(labelLayout(room, 1000, 1000, 1).visible).toBe(false)
    // Zoomed in far enough it fits again (32px cap, box 500px).
    expect(labelLayout(room, 1000, 1000, 0.1).visible).toBe(true)

    // A caption only a little too wide shrinks to fit instead of vanishing.
    const narrow = shape({
      label: 'Spielwiese',
      points: [
        [0.1, 0.1],
        [0.16, 0.4],
      ],
    })
    const nominalPx = 26
    expect(estimateTextWidth('Spielwiese', nominalPx)).toBeGreaterThan(60 + 8)
    const fitted = labelLayout(narrow, 1000, 1000, 1)
    expect(fitted.visible).toBe(true)
    expect(fitted.fontUnits).toBeLessThan(nominalPx)
    expect(fitted.fontUnits).toBeGreaterThanOrEqual(11)
    expect(estimateTextWidth('Spielwiese', fitted.fontUnits)).toBeLessThanOrEqual(68 + 1e-6)

    const polygon = { ...room, kind: 'polygon' as const, points: [...room.points, [0.1, 0.2]] }
    expect(labelLayout(polygon, 1000, 1000, 1).visible).toBe(false)

    const path = shape({
      kind: 'path',
      label: text,
      points: [
        [0.1, 0.1],
        [0.12, 0.1],
      ],
    })
    expect(labelLayout(path, 1000, 1000, 1).visible).toBe(true)
    const free = shape({ kind: 'label', label: text, points: [[0.1, 0.1]] })
    expect(labelLayout(free, 1000, 1000, 1).visible).toBe(true)
  })
})

describe('markers', () => {
  const area = (id: string, location_id: string | null, sort_order: number, kind = 'rect') =>
    ({
      ...shape({ id, location_id, sort_order, kind: kind as RenderShape['kind'] }),
      plan_id: 'p1',
    }) as VenueShapeRead

  it('sorts by sort_order, then id', () => {
    const list = [
      { id: 'b', sort_order: 1 },
      { id: 'c', sort_order: 0 },
      { id: 'a', sort_order: 1 },
      { id: 'a', sort_order: 1 },
    ]
    expect(sortShapes(list).map((s) => s.id)).toEqual(['c', 'a', 'a', 'b'])
    expect(list[0]!.id).toBe('b') // not in place
  })

  it('makes one virtual pill per unmarked linked place, at its first area', () => {
    const marker: VenueMarkerRead = {
      id: 'm1',
      plan_id: 'p1',
      kind: 'location',
      location_id: 'loc-marked',
      x: 0.9,
      y: 0.9,
    }
    const generic: VenueMarkerRead = { id: 'm2', plan_id: 'p1', kind: 'toilets', x: 0, y: 0 }
    const second = {
      ...area('s-second', 'loc-a', 5),
      points: [
        [0.6, 0.6],
        [0.8, 0.8],
      ],
    }
    const plan = {
      id: 'p1',
      markers: [marker, generic],
      shapes: [
        second,
        area('s-first', 'loc-a', 1),
        area('s-marked', 'loc-marked', 0),
        area('s-free', null, 2),
        area('s-path', 'loc-b', 3, 'path'),
        area('s-poly', 'loc-c', 4, 'polygon'),
      ],
    }
    const virtual = virtualMarkers(plan)
    expect(virtual.map((m) => m.id)).toEqual(['shape:s-first', 'shape:s-poly'])
    expect(virtual[0]).toEqual({
      id: 'shape:s-first',
      plan_id: 'p1',
      kind: 'location',
      location_id: 'loc-a',
      label: null,
      x: 0.3,
      y: 0.4,
    })
    expect(planMarkers(plan).map((m) => m.id)).toEqual([
      'm1',
      'm2',
      'shape:s-first',
      'shape:s-poly',
    ])
    expect(virtualMarkers({ id: 'p1' })).toEqual([])
    expect(isVirtualMarkerId('shape:s-first')).toBe(true)
    expect(isVirtualMarkerId('m1')).toBe(false)
  })
})
