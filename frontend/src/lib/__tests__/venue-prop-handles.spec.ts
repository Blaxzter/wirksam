import { describe, expect, it } from 'vitest'

import {
  RESIZE_GRIP_ANGLE,
  RING_GAP_PX,
  angleFromCentre,
  distance,
  pointAtAngle,
  propGrips,
  propRingRadius,
  resizeCursor,
  rotationFromDrag,
  roundScale,
  scaleFromDrag,
  scaleStartDistance,
  snapAngle,
} from '@/lib/venue-prop-handles'

const C = { x: 100, y: 100 }

describe('angleFromCentre', () => {
  it('measures clockwise from up, with y growing downwards', () => {
    expect(angleFromCentre(C, { x: 100, y: 50 })).toBe(0)
    expect(angleFromCentre(C, { x: 150, y: 100 })).toBe(90)
    expect(angleFromCentre(C, { x: 100, y: 150 })).toBe(180)
    expect(angleFromCentre(C, { x: 50, y: 100 })).toBe(270)
    expect(angleFromCentre(C, { x: 150, y: 150 })).toBe(135)
  })
})

describe('pointAtAngle', () => {
  it('is the inverse of angleFromCentre', () => {
    for (const angle of [0, 45, 90, 200, 315]) {
      const p = pointAtAngle(C, angle, 30)
      expect(angleFromCentre(C, p)).toBeCloseTo(angle)
      expect(distance(C, p)).toBeCloseTo(30)
    }
    const up = pointAtAngle(C, 0, 10)
    expect(up.x).toBeCloseTo(100)
    expect(up.y).toBeCloseTo(90)
  })
})

describe('snapAngle', () => {
  it('rounds to the step and wraps at 360', () => {
    expect(snapAngle(7)).toBe(0)
    expect(snapAngle(8)).toBe(15)
    expect(snapAngle(353)).toBe(0)
    expect(snapAngle(-20)).toBe(345)
    expect(snapAngle(44, 45)).toBe(45)
  })

  it('leaves the angle as it is without a usable step', () => {
    expect(snapAngle(33.3, 0)).toBe(33.3)
    expect(snapAngle(-10, Number.NaN)).toBe(350)
  })
})

describe('rotationFromDrag', () => {
  it('turns by as much as the pointer went round the centre', () => {
    expect(rotationFromDrag(0, 0, 90)).toBe(90)
    // Grabbed off-centre at 10°: no jump, only the difference counts.
    expect(rotationFromDrag(30, 10, 10)).toBe(30)
    expect(rotationFromDrag(30, 10, 50)).toBe(70)
    // Across "up" in either direction.
    expect(rotationFromDrag(10, 350, 20)).toBe(40)
    expect(rotationFromDrag(10, 20, 350)).toBe(340)
  })

  it('snaps the result to 15° when asked', () => {
    expect(rotationFromDrag(0, 0, 52, true)).toBe(45)
    expect(rotationFromDrag(5, 0, 52, true)).toBe(60)
    expect(rotationFromDrag(0, 0, 359, true)).toBe(0)
  })
})

describe('scaleFromDrag', () => {
  it('scales by the distance ratio, clamped and rounded', () => {
    expect(scaleFromDrag(1, 20, 40)).toBe(2)
    expect(scaleFromDrag(1.5, 30, 10)).toBe(0.5)
    expect(scaleFromDrag(1, 3, 4)).toBe(1.333)
    expect(scaleFromDrag(1, 10, 1000)).toBe(4)
    expect(scaleFromDrag(1, 10, 0)).toBe(0.25)
    expect(scaleFromDrag(1, 10, -5)).toBe(0.25)
  })

  it('holds the size when the press was on the centre or the distance is bad', () => {
    expect(scaleFromDrag(1.2, 0, 50)).toBe(1.2)
    expect(scaleFromDrag(1.2, Number.NaN, 50)).toBe(1.2)
    expect(scaleFromDrag(1.2, 10, Number.POSITIVE_INFINITY)).toBe(1.2)
    expect(scaleFromDrag(9, 0, 50)).toBe(4)
  })

  it('rounds like a stored size', () => {
    expect(roundScale(1.23456)).toBe(1.235)
  })
})

describe('resizeCursor', () => {
  it('picks the double arrow closest to the grip direction', () => {
    expect(resizeCursor(0)).toBe('ns-resize')
    expect(resizeCursor(180)).toBe('ns-resize')
    expect(resizeCursor(45)).toBe('nesw-resize')
    expect(resizeCursor(225)).toBe('nesw-resize')
    expect(resizeCursor(90)).toBe('ew-resize')
    expect(resizeCursor(135)).toBe('nwse-resize')
    expect(resizeCursor(-45)).toBe('nwse-resize')
    expect(resizeCursor(350)).toBe('ns-resize')
  })
})

describe('propGrips', () => {
  it('puts the rotate grip above the ring and the resize grip at the bottom right', () => {
    const g = propGrips(C, 0, 20, 10)
    expect(g.ring).toBe(20)
    expect(g.stalk.x).toBeCloseTo(100)
    expect(g.stalk.y).toBeCloseTo(80)
    expect(g.rotate.x).toBeCloseTo(100)
    expect(g.rotate.y).toBeCloseTo(70)
    expect(g.resizeAngle).toBe(RESIZE_GRIP_ANGLE)
    expect(g.resize.x).toBeGreaterThan(100)
    expect(g.resize.y).toBeGreaterThan(100)
    expect(distance(C, g.resize)).toBeCloseTo(20)
  })

  it('turns both grips with the glyph', () => {
    const g = propGrips(C, 90, 20, 10)
    expect(g.rotate.x).toBeCloseTo(130)
    expect(g.rotate.y).toBeCloseTo(100)
    expect(g.resizeAngle).toBe(225)
    expect(propGrips(C, 300, 20, 10).resizeAngle).toBe(75)
  })
})

describe('resize grip hit circle', () => {
  it('stays on the ring when its hit circle already clears the glyph', () => {
    const g = propGrips(C, 0, 40, 10, 36, 3)
    expect(distance(C, g.resizeHit)).toBeCloseTo(40)
    expect(g.resizeHit.x).toBeCloseTo(g.resize.x)
  })

  it('moves outwards on a small glyph, so a press on the glyph is not a resize', () => {
    // A 8-unit glyph, ring 12, a 20-unit hit circle (a finger at default zoom).
    const glyph = 8
    const hit = 20
    const g = propGrips(C, 30, 12, 28, glyph, hit)
    const reach = distance(C, g.resizeHit)
    expect(reach).toBeCloseTo(glyph + hit)
    // The circle never reaches inside the glyph, nor the centre …
    expect(reach - hit).toBeGreaterThanOrEqual(glyph - 1e-9)
    // … and the visible grip on the ring is still inside it.
    expect(distance(g.resize, g.resizeHit)).toBeLessThan(hit)
    // Same direction as the visible grip.
    expect(angleFromCentre(C, g.resizeHit)).toBeCloseTo(g.resizeAngle)
  })

  it('defaults to the ring without a glyph or hit radius', () => {
    const g = propGrips(C, 0, 20, 10)
    expect(g.resizeHit).toEqual(g.resize)
  })
})

describe('propRingRadius', () => {
  it('is the glyph radius plus a constant on-screen gap', () => {
    expect(propRingRadius(10, 1)).toBe(10 + RING_GAP_PX)
    expect(propRingRadius(10, 0.5)).toBe(10 + RING_GAP_PX / 2)
  })
})

describe('scaleStartDistance', () => {
  it('never measures from nearer than the glyph', () => {
    expect(scaleStartDistance(2, 12)).toBe(12)
    expect(scaleStartDistance(0, 12)).toBe(12)
    expect(scaleStartDistance(30, 12)).toBe(30)
  })

  it('does not jump for a press anywhere the grip can be pressed', () => {
    // Glyph radius 8: a press 9 units out, nudged by nothing, keeps its size.
    expect(scaleFromDrag(1, scaleStartDistance(9, 8), 9)).toBe(1)
  })

  it('keeps a near-centre press from jumping to the size limit', () => {
    const start = scaleStartDistance(2, 12)
    // 40 units further out from a press 2 units off-centre.
    expect(scaleFromDrag(1, start, 42)).toBeLessThan(4)
    expect(scaleFromDrag(1, 2, 42)).toBe(4)
  })
})
