import { describe, expect, it } from 'vitest'

import { hexToOklch } from '@/lib/colour-math'
import { TARGET, baseStrength, customColour, registerCustomColour } from '@/lib/custom-colour'

/**
 * An own colour, worked out into the variables a preset has. That every
 * result reads at 4.5:1 on every palette is checked against the stylesheet in
 * `event-colour-contrast.spec.ts`; this covers what the organisers are told.
 */

describe('an own main colour', () => {
  it('stays as picked in light mode when it already reads, and lightens for dark mode', () => {
    const navy = customColour('primary', '#1e3a8a')
    expect(navy.report!.light).toMatchObject({ used: '#1e3a8a', adjusted: false })
    expect(navy.report!.light.ratio).toBeGreaterThanOrEqual(TARGET)
    expect(navy.report!.dark.adjusted).toBe(true)
    expect(hexToOklch(navy.report!.dark.used).l).toBeGreaterThan(hexToOklch('#1e3a8a').l)
    expect(navy.report!.dark.ratio).toBeGreaterThanOrEqual(TARGET)
    expect(navy.report!.dark.originalRatio).toBeLessThan(4.5)
  })

  it('darkens a colour too pale to read as text, keeping its hue', () => {
    const pale = customColour('primary', '#ffd54f')
    const { light } = pale.report!
    expect(light.adjusted).toBe(true)
    expect(light.originalRatio).toBeLessThan(4.5)
    expect(light.ratio).toBeGreaterThanOrEqual(TARGET)
    expect(hexToOklch(light.used).h).toBeCloseTo(hexToOklch('#ffd54f').h, -1)
  })

  it('becomes a preset under its own name, light and dark', () => {
    const { css } = customColour('primary', '#1e6bb8')
    expect(css).toContain("[data-event-primary='#1e6bb8'] {")
    expect(css).toContain(
      ".dark [data-event-primary='#1e6bb8'],\n.dark[data-event-primary='#1e6bb8'] {",
    )
    for (const name of ['primary', 'primary-foreground', 'primary-hero', 'primary-hue']) {
      expect(css).toContain(`--event-${name}:`)
    }
  })
})

describe('an own second colour', () => {
  it('stays as picked when dark text already reads on it', () => {
    const yellow = customColour('secondary', '#ffcc00')
    expect(yellow.report!.light).toMatchObject({ used: '#ffcc00', adjusted: false })
    expect(yellow.report!.dark.adjusted).toBe(false)
  })

  it('lightens a dark one until dark text reads on it', () => {
    const { light } = customColour('secondary', '#1e3a8a').report!
    expect(light.adjusted).toBe(true)
    expect(light.ratio).toBeGreaterThanOrEqual(TARGET)
    expect(hexToOklch(light.used).l).toBeGreaterThan(hexToOklch('#1e3a8a').l)
  })

  it('brings the soft and pale surfaces the presets have', () => {
    const { css } = customColour('secondary', '#2e7d32')
    for (const name of [
      'secondary',
      'secondary-soft',
      'secondary-soft-foreground',
      'secondary-pale',
    ]) {
      expect(css).toContain(`--event-${name}:`)
    }
  })
})

describe('an own base tone', () => {
  it('lends only its hue and a strength, and tells nothing to adjust', () => {
    const green = customColour('base', '#2e7d32')
    expect(green.report).toBeNull()
    expect(green.css).toMatch(/--event-base-hue: [\d.]+;/)
    expect(green.css).toMatch(/--event-base-chroma: [\d.]+;/)
    expect(green.css).not.toContain('.dark')
  })

  it('tints as strongly as the colour is colourful: none for grey, up to the strongest preset', () => {
    expect(baseStrength(hexToOklch('#808080'))).toBe(0)
    expect(baseStrength(hexToOklch('#ff0000'))).toBe(1.5)
    const muted = baseStrength(hexToOklch('#8a9a8a'))
    expect(muted).toBeGreaterThanOrEqual(0)
    expect(muted).toBeLessThan(1.5)
  })
})

describe('customColour', () => {
  it('takes the colour in either case and works it out once', () => {
    const a = customColour('primary', '#1E6BB8')
    expect(a.hex).toBe('#1e6bb8')
    expect(customColour('primary', '#1e6bb8')).toBe(a)
  })

  it('refuses something that is not a colour', () => {
    expect(() => customColour('primary', 'blue')).toThrow()
  })
})

describe('registerCustomColour without a page', () => {
  it('answers the attribute value and has nothing to write to', () => {
    expect(registerCustomColour('primary', '#ABCDEF')).toBe('#abcdef')
  })
})
