import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

import {
  DEFAULT_PROP_SCALE,
  FALLBACK_GLYPH,
  type GlyphPart,
  LINE_PAINTS,
  LINE_PRESETS,
  PROP_GROUPS,
  PROP_META,
  PROP_SCALE_RANGE,
  PROP_TYPES,
  ROTATION_STEP,
  SHADOW_OFFSET,
  clampPropScale,
  isPropType,
  normaliseRotation,
  postsAlong,
  postsPath,
  propGlyph,
  propLabelKey,
  propPaintClass,
  propPlacement,
  propUnit,
  sortProps,
} from '@/lib/venue-decor'

// Read from disk: Vitest hands CSS imports back empty.
const css = readFileSync(new URL('../../index.css', import.meta.url), 'utf8')

const allParts = (prop: string): GlyphPart[] => {
  const g = propGlyph(prop)
  return [...g.shadow, ...g.body]
}

describe('the prop catalogue', () => {
  it('lists the 14 backend props, each with meta and a glyph', () => {
    expect(PROP_TYPES).toHaveLength(14)
    for (const prop of PROP_TYPES) {
      const meta = PROP_META[prop]
      expect(meta.size).toBeGreaterThan(0)
      const glyph = propGlyph(prop)
      expect(glyph.body.length).toBeGreaterThan(0)
      expect(glyph.radius).toBe(meta.radius)
    }
  })

  it('groups every prop exactly once, in catalogue order', () => {
    const grouped = [...PROP_GROUPS.nature, ...PROP_GROUPS.furniture, ...PROP_GROUPS.event]
    expect(grouped).toEqual([...PROP_TYPES])
    expect(PROP_GROUPS.nature).toEqual(['tree', 'conifer', 'bush', 'flowers', 'plant'])
    expect(PROP_GROUPS.event).toEqual(['parasol', 'tent', 'lamp'])
  })

  it('has a .vp-<paint> rule in index.css for every paint a glyph uses', () => {
    const paints = new Set(
      [...PROP_TYPES, 'unknown'].flatMap((p) => allParts(p).map((part) => part.paint)),
    )
    for (const paint of paints) {
      expect([paint, css.includes(`.${propPaintClass(paint)}`)]).toEqual([paint, true])
    }
  })

  it('gives every line paint a width and every fill paint none', () => {
    for (const prop of PROP_TYPES) {
      for (const part of allParts(prop)) {
        if (LINE_PAINTS.has(part.paint)) {
          expect(part.el).toBe('path')
          expect(part.el === 'path' && part.strokeWidth).toBeGreaterThan(0)
        } else if (part.el === 'path') {
          expect(part.strokeWidth).toBeUndefined()
        }
      }
    }
  })

  it('draws an unknown or missing prop as the fallback glyph', () => {
    expect(propGlyph('nope')).toBe(FALLBACK_GLYPH)
    expect(propGlyph(null)).toBe(FALLBACK_GLYPH)
    expect(propGlyph(undefined)).toBe(FALLBACK_GLYPH)
    expect(FALLBACK_GLYPH.radius).toBe(10)
    expect(isPropType('tree')).toBe(true)
    expect(isPropType('toString')).toBe(false)
    expect(isPropType(3)).toBe(false)
  })

  it('names classes and i18n keys', () => {
    expect(propPaintClass('leaf-hi')).toBe('vp-leaf-hi')
    expect(propLabelKey('picnic_table')).toBe('venueMap.props.picnic_table')
  })

  it('exposes the editor constants', () => {
    expect(PROP_SCALE_RANGE).toEqual([0.25, 4])
    expect(DEFAULT_PROP_SCALE).toBe(1)
    expect(ROTATION_STEP).toBe(15)
    expect(SHADOW_OFFSET).toEqual([2.5, 3.5])
  })
})

describe('rotation and scale', () => {
  it('normalises rotation like the backend', () => {
    expect(normaliseRotation(-90)).toBe(270)
    expect(normaliseRotation(360)).toBe(0)
    expect(normaliseRotation(725.3)).toBe(5.3)
    expect(normaliseRotation(359.96)).toBe(0)
    expect(normaliseRotation(Number.NaN)).toBe(0)
  })

  it('clamps scale to the allowed range', () => {
    expect(clampPropScale(0.1)).toBe(0.25)
    expect(clampPropScale(9)).toBe(4)
    expect(clampPropScale(1.5)).toBe(1.5)
    expect(clampPropScale(Number.POSITIVE_INFINITY)).toBe(1)
  })

  it('sizes a prop by the plan’s shorter side', () => {
    // tree: 0.055 of 1000 over 48 units.
    expect(propUnit('tree', 1, 1600, 1000)).toBeCloseTo((0.055 * 1000) / 48)
    expect(propUnit('tree', 2, 1000, 1600)).toBeCloseTo((0.055 * 1000 * 2) / 48)
    expect(propUnit('tree', null, 1600, 1000)).toBeCloseTo((0.055 * 1000) / 48)
    expect(propUnit('mystery', 1, 480, 480)).toBeCloseTo(0.3)
  })
})

describe('propPlacement', () => {
  const W = 480
  const H = 960
  // tree at scale 1 on a 480-wide plan: k = 0.055 * 480 / 48 = 0.55.
  const tree = { points: [[0.5, 0.25]], prop: 'tree' as const, rotation: 0, scale: 1 }

  it('builds the transforms, omitting a zero rotation', () => {
    const p = propPlacement(tree, W, H)
    expect(p).toMatchObject({ x: 240, y: 240, rotation: 0 })
    expect(p.k).toBeCloseTo(0.55)
    expect(p.body).toBe('translate(240 240) scale(0.55)')
    expect(p.shadow).toBe('translate(241.375 241.925) scale(0.55)')
    expect(p.radiusUnits).toBeCloseTo(24 * 0.55)
  })

  it('turns the body but never the sun', () => {
    const turned = propPlacement({ ...tree, rotation: 90 }, W, H)
    expect(turned.body).toBe('translate(240 240) rotate(90) scale(0.55)')
    expect(turned.shadow).toBe('translate(241.375 241.925) rotate(90) scale(0.55)')
    const flat = propPlacement(tree, W, H)
    expect(turned.shadow.split(' rotate')[0]).toBe(flat.shadow.split(' scale')[0])
  })

  it('copes with missing fields', () => {
    const p = propPlacement({ points: [], prop: null, rotation: null, scale: null }, W, H)
    expect(p).toMatchObject({ x: 0, y: 0, rotation: 0 })
    expect(p.radiusUnits).toBeCloseTo(10 * ((0.03 * 480) / 48))
  })
})

describe('sortProps', () => {
  it('draws the ground tier first, then by sort_order and id', () => {
    const list = [
      { id: 'b', prop: 'tree', sort_order: 0 },
      { id: 'a', prop: 'bench', sort_order: 5 },
      { id: 'c', prop: 'flowers', sort_order: 1 },
      { id: 'e', prop: 'tent', sort_order: 0 },
      { id: 'd', prop: 'mystery', sort_order: 1 },
      { id: 'f', prop: 'bench', sort_order: 5 },
    ]
    expect(sortProps(list).map((p) => p.id)).toEqual(['c', 'd', 'a', 'f', 'b', 'e'])
    // Does not mutate its input.
    expect(list[0]!.id).toBe('b')
  })
})

describe('postsAlong', () => {
  it('spaces posts evenly along a straight line, both ends included', () => {
    const posts = postsAlong(
      [
        [0, 0],
        [100, 0],
      ],
      25,
    )
    expect(posts.map((p) => p.x)).toEqual([0, 25, 50, 75, 100])
    expect(posts.every((p) => p.y === 0 && p.angle === 0)).toBe(true)
  })

  it('follows the bends and turns each post to its edge', () => {
    const posts = postsAlong(
      [
        [0, 0],
        [10, 0],
        [10, 10],
      ],
      5,
    )
    expect(posts).toHaveLength(5)
    expect(posts[3]).toEqual({ x: 10, y: 5, angle: 90 })
    expect(posts[4]).toEqual({ x: 10, y: 10, angle: 90 })
  })

  it('closes an outline without a duplicate post at the seam', () => {
    const square: [number, number][] = [
      [0, 0],
      [10, 0],
      [10, 10],
      [0, 10],
    ]
    const posts = postsAlong(square, 10, { closed: true })
    expect(posts.map((p) => [p.x, p.y])).toEqual(square)
  })

  it('caps the count', () => {
    const line: [number, number][] = [
      [0, 0],
      [10000, 0],
    ]
    expect(postsAlong(line, 1)).toHaveLength(200)
    expect(postsAlong(line, 1, { max: 10 })).toHaveLength(10)
    expect(postsAlong(line, 1, { max: 1 })).toHaveLength(1)
    expect(postsAlong(line, 0)).toHaveLength(2)
  })

  it('handles empty and zero-length lines', () => {
    expect(postsAlong([], 10)).toEqual([])
    expect(
      postsAlong(
        [
          [3, 4],
          [3, 4],
        ],
        10,
      ),
    ).toEqual([{ x: 3, y: 4, angle: 0 }])
  })
})

describe('postsPath', () => {
  it('draws one square per post, turned to its angle', () => {
    expect(postsPath([{ x: 10, y: 20, angle: 0 }], 2)).toBe('M9 19L11 19L11 21L9 21Z')
    const turned = postsPath([{ x: 0, y: 0, angle: 45 }], 2)
    expect(turned).toMatch(/^M0 -1\.4142L1\.4142 0L0 1\.4142L-1\.4142 0Z$/)
    expect(postsPath([], 2)).toBe('')
  })
})

describe('LINE_PRESETS', () => {
  it('stays within the backend stroke range', () => {
    for (const [key, preset] of Object.entries(LINE_PRESETS)) {
      expect(preset.style).toBe(key)
      expect(preset.strokeWidth).toBeGreaterThanOrEqual(0.002)
      expect(preset.strokeWidth).toBeLessThanOrEqual(0.2)
    }
    expect(LINE_PRESETS.hedge.strokeWidth).toBe(0.016)
    expect(LINE_PRESETS.fence.strokeWidth).toBe(0.008)
  })
})
