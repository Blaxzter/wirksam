import { describe, expect, it } from 'vitest'

import {
  contrast,
  fitToGamut,
  hexToOklch,
  isHexColour,
  oklchCss,
  oklchToHex,
  oklchToLinearRgb,
  oklchToLinearRgbRaw,
  over,
  rgbOf,
} from '@/lib/colour-math'

/** OKLCH and sRGB hex, both ways, and WCAG contrast. */

describe('isHexColour', () => {
  it('takes six hex digits after a hash, in either case', () => {
    for (const value of ['#1e6bb8', '#1E6BB8', '#000000']) expect(isHexColour(value)).toBe(true)
    for (const value of ['1e6bb8', '#1e6bb', '#1e6bb8f', '#ggg000', 'blue', null, 3]) {
      expect(isHexColour(value)).toBe(false)
    }
  })
})

describe('hexToOklch and oklchToHex', () => {
  it('puts white, black and grey on the lightness axis', () => {
    expect(hexToOklch('#ffffff').l).toBeCloseTo(1, 3)
    expect(hexToOklch('#000000').l).toBeCloseTo(0, 3)
    const grey = hexToOklch('#808080')
    expect(grey.c).toBeLessThan(0.001)
    expect(grey.h).toBe(0)
  })

  it('finds the hue of a colour', () => {
    expect(hexToOklch('#ff0000').h).toBeCloseTo(29.2, 0)
    expect(hexToOklch('#0000ff').h).toBeCloseTo(264.1, 0)
  })

  it('gets back the colour it started from', () => {
    for (const hex of ['#1e6bb8', '#ffcc00', '#2e7d32', '#fffde7', '#5b2c6f', '#ff0000']) {
      expect(oklchToHex(hexToOklch(hex))).toBe(hex)
    }
  })

  it('refuses something that is not a colour', () => {
    expect(() => hexToOklch('blue')).toThrow()
  })
})

describe('fitToGamut', () => {
  it('leaves a colour a screen can show alone', () => {
    const blue = hexToOklch('#1e6bb8')
    expect(fitToGamut(blue)).toEqual(blue)
  })

  it('gives up chroma, never lightness or hue, for one it cannot', () => {
    const vivid = { l: 0.95, c: 0.3, h: 260 }
    const fitted = fitToGamut(vivid)
    expect(fitted.l).toBe(0.95)
    expect(fitted.h).toBe(260)
    expect(fitted.c).toBeLessThan(0.3)
    expect(
      oklchToLinearRgbRaw(fitted.l, fitted.c, fitted.h).every((x) => x >= -1e-3 && x <= 1.001),
    ).toBe(true)
  })
})

describe('contrast', () => {
  it('is 21 for black on white and 1 for a colour on itself', () => {
    expect(contrast(rgbOf({ l: 0, c: 0, h: 0 }), rgbOf({ l: 1, c: 0, h: 0 }))).toBeCloseTo(21, 1)
    expect(contrast(oklchToLinearRgb(0.5, 0.1, 200), oklchToLinearRgb(0.5, 0.1, 200))).toBe(1)
  })

  it('reads the same either way round', () => {
    const a = rgbOf({ l: 0.4, c: 0.1, h: 250 })
    const b = rgbOf({ l: 0.9, c: 0.02, h: 80 })
    expect(contrast(a, b)).toBe(contrast(b, a))
  })
})

describe('over', () => {
  it('lies between the two colours', () => {
    const black = rgbOf({ l: 0, c: 0, h: 0 })
    const white = rgbOf({ l: 1, c: 0, h: 0 })
    const mixed = over(black, 0.5, white)
    expect(mixed[0]).toBeGreaterThan(0)
    expect(mixed[0]).toBeLessThan(1)
    expect(over(black, 0, white)).toEqual(white)
  })
})

describe('oklchCss', () => {
  it('writes a CSS value, fitted and rounded', () => {
    expect(oklchCss({ l: 0.471234, c: 0.140123, h: 258.1234 })).toBe('oklch(0.4712 0.1401 258.12)')
    expect(oklchCss({ l: 0.95, c: 0.3, h: 260 })).toMatch(/^oklch\(0\.95 0\.0\d+ 260\)$/)
  })
})
