import { describe, expect, it } from 'vitest'

import { isHexColour, oklchToHex } from '@/lib/colour-math'
import { type ColourKind, SURFACES, customColour } from '@/lib/custom-colour'
import {
  EVENT_BASE_COLORS,
  EVENT_PRIMARY_COLORS,
  EVENT_SECONDARY_COLORS,
} from '@/lib/event-appearance'

import { type Rgb, type Tokens, colour, contrast, css, declarations, over } from './css-tokens'

/**
 * WCAG 2.x contrast of the event colour presets ("Event colours" in
 * `index.css`), recomputed from the stylesheet, so a retuned or added preset
 * cannot make buttons, links or chips unreadable in some event.
 *
 * An event's colours replace tokens on top of whichever palette the viewer
 * chose, so every preset is checked against both palettes, in light and in
 * dark mode, and every primary with every secondary and every base tone
 * (and with none):
 *
 * - primary: text on a primary button, hero text on the hero panel, the
 *   active sidebar item, and the primary as text on the background, cards,
 *   muted surfaces and the sidebar, also over its own `/15` tint: 4.5:1. The
 *   focus ring against the background: 3:1.
 * - secondary: text on the secondary surfaces (secondary buttons, hover and
 *   selected rows, the active sidebar row) and on the chip: 4.5:1. Muted text
 *   on those surfaces: 4.5:1, or in the classic palette no worse than on that
 *   palette's own muted grey (which sits just under 4.5:1 by itself).
 * - the default palette's neutrals, which take the base tone's hue (and in
 *   dark mode the primary's without one): the same pairs as the palette's own
 *   text on its own surfaces, and the primary and secondary pairs above on
 *   the tinted surfaces.
 *
 * An own colour (`#rrggbb`) is worked out at runtime (`custom-colour.ts`), so
 * the same pairs are checked for colours from all round the colour wheel, at
 * every lightness and strength, with the rules it would put on the page.
 */

type PaletteName = 'default light' | 'default dark' | 'classic light' | 'classic dark'

const PALETTES: Record<PaletteName, Tokens> = {
  'default light': declarations((s) => s === ':root'),
  'default dark': new Map([
    ...declarations((s) => s === ':root'),
    ...declarations((s) => s === '.dark'),
  ]),
  'classic light': new Map([
    ...declarations((s) => s === ':root'),
    ...declarations((s) => s === '.palette-classic'),
  ]),
  'classic dark': new Map([
    ...declarations((s) => s === ':root'),
    ...declarations((s) => s === '.dark'),
    ...declarations((s) => s === '.palette-classic'),
    ...declarations((s) => s === '.palette-classic.dark'),
  ]),
}

const ON_PRIMARY = ':root[data-event-primary]'
const ON_SECONDARY = ':root[data-event-secondary]'
const CLASSIC_LIGHT_SECONDARY = ':root.palette-classic:not(.dark)[data-event-secondary]'
const DARK_NEUTRALS = ':root.dark[data-event-primary]:not(.palette-classic)'
const DARK_SURFACES =
  ':root.dark[data-event-primary]:not(.palette-classic):not([data-event-secondary])'
const BASE_LIGHT = ':root[data-event-base]:not(.dark):not(.palette-classic)'
const BASE_LIGHT_SURFACES =
  ':root[data-event-base]:not(.dark):not(.palette-classic):not([data-event-secondary])'
const BASE_DARK = ':root.dark[data-event-base]:not(.palette-classic)'
const BASE_DARK_SURFACES =
  ':root.dark[data-event-base]:not(.palette-classic):not([data-event-secondary])'
// Thousands of pairings read the same few rules: parse each once.
const rules = new Map<string, Tokens>()
const rule = (selector: string) => {
  if (!rules.has(selector))
    rules.set(
      selector,
      declarations((s) => s === selector),
    )
  return rules.get(selector)!
}

/** A preset's rule, from index.css, or from the rules an own colour would put on the page. */
const presetRule = (kind: ColourKind, value: string, selector: string) =>
  isHexColour(value)
    ? declarations((s) => s === selector, customColour(kind, value).css)
    : rule(selector)

/**
 * The tokens of a palette with the event's colours on <html>, as the browser
 * resolves them. A base tone that follows a primary the event lacks is left
 * off, as `useEventColors` does.
 */
function dressed(
  name: PaletteName,
  primary: string | null,
  secondary: string | null,
  base: string | null = null,
): Tokens {
  const dark = name.endsWith('dark')
  const classic = name.startsWith('classic')
  const tone = base === 'primary' && !primary ? null : base
  const toned = !!tone && !classic
  const preset = (kind: 'primary' | 'secondary', value: string | null) =>
    value
      ? [
          ...presetRule(kind, value, `[data-event-${kind}='${value}']`),
          ...(dark ? presetRule(kind, value, `.dark[data-event-${kind}='${value}']`) : []),
        ]
      : []
  return new Map([
    ...PALETTES[name],
    ...preset('primary', primary),
    ...preset('secondary', secondary),
    ...(primary ? rule(ON_PRIMARY) : []),
    ...(secondary ? rule(ON_SECONDARY) : []),
    ...(secondary && classic && !dark ? rule(CLASSIC_LIGHT_SECONDARY) : []),
    ...(primary && dark && !classic ? rule(DARK_NEUTRALS) : []),
    ...(primary && dark && !classic && !secondary ? rule(DARK_SURFACES) : []),
    ...(tone ? presetRule('base', tone, `[data-event-base='${tone}']`) : []),
    ...(toned ? rule(dark ? BASE_DARK : BASE_LIGHT) : []),
    ...(toned && !secondary ? rule(dark ? BASE_DARK_SURFACES : BASE_LIGHT_SURFACES) : []),
  ])
}

type Pair = { label: string; fg: Rgb; bg: Rgb; min: number }
const TEXT = 4.5
const UI = 3

function primaryPairs(t: Tokens): Pair[] {
  const c = (name: string) => colour(t, name)
  const list: Pair[] = [
    {
      label: 'button text on the primary',
      fg: c('--primary-foreground'),
      bg: c('--primary'),
      min: TEXT,
    },
    { label: 'hero text on the hero', fg: c('--hero-foreground'), bg: c('--hero'), min: TEXT },
    {
      label: 'active sidebar item text',
      fg: c('--sidebar-primary-foreground'),
      bg: c('--sidebar-primary'),
      min: TEXT,
    },
    { label: 'focus ring on the background', fg: c('--ring'), bg: c('--background'), min: UI },
  ]
  for (const surface of ['--background', '--card', '--muted', '--sidebar']) {
    list.push({
      label: `primary text on ${surface}`,
      fg: c('--primary'),
      bg: c(surface),
      min: TEXT,
    })
  }
  for (const surface of ['--background', '--card']) {
    list.push({
      label: `primary text on its /15 tint over ${surface}`,
      fg: c('--primary'),
      bg: over(c('--primary'), 0.15, c(surface)),
      min: TEXT,
    })
  }
  return list
}

function secondaryPairs(t: Tokens, mutedMin: number): Pair[] {
  const c = (name: string) => colour(t, name)
  const list: Pair[] = [
    {
      label: 'text on a secondary surface',
      fg: c('--secondary-foreground'),
      bg: c('--secondary'),
      min: TEXT,
    },
    { label: 'text on a hovered row', fg: c('--accent-foreground'), bg: c('--accent'), min: TEXT },
    {
      label: 'text on the active sidebar row',
      fg: c('--sidebar-accent-foreground'),
      bg: c('--sidebar-accent'),
      min: TEXT,
    },
    {
      label: 'chip text on the chip',
      fg: c('--hero-chip-foreground'),
      bg: c('--hero-chip'),
      min: TEXT,
    },
  ]
  for (const surface of ['--secondary', '--accent']) {
    list.push({
      label: `muted text on ${surface}`,
      fg: c('--muted-foreground'),
      bg: c(surface),
      min: mutedMin,
    })
  }
  return list
}

function neutralPairs(t: Tokens): Pair[] {
  const c = (name: string) => colour(t, name)
  return [
    { label: 'text on the background', fg: c('--foreground'), bg: c('--background'), min: TEXT },
    { label: 'text on a card', fg: c('--card-foreground'), bg: c('--card'), min: TEXT },
    { label: 'text in the sidebar', fg: c('--sidebar-foreground'), bg: c('--sidebar'), min: TEXT },
    ...['--background', '--card', '--muted'].map((surface) => ({
      label: `muted text on ${surface}`,
      fg: c('--muted-foreground'),
      bg: c(surface),
      min: TEXT,
    })),
  ]
}

/** How readable muted text is on the palette's own muted surface: the bar for the classic palette. */
function mutedBar(name: PaletteName): number {
  const t = PALETTES[name]
  const own = contrast(colour(t, '--muted-foreground'), colour(t, '--muted'))
  return Math.min(TEXT, own)
}

/** Every pair an event with these colours changes, on this palette. */
function pairsFor(
  name: PaletteName,
  primary: string | null,
  secondary: string | null,
  base: string | null = null,
): Pair[] {
  const t = dressed(name, primary, secondary, base)
  const retinted = (!!primary && name === 'default dark') || (!!base && name.startsWith('default'))
  return [
    ...(primary || retinted ? primaryPairs(t) : []),
    ...(secondary || retinted ? secondaryPairs(t, mutedBar(name)) : []),
    ...(retinted ? neutralPairs(t) : []),
  ]
}

const paletteNames = Object.keys(PALETTES) as PaletteName[]

describe.each(EVENT_PRIMARY_COLORS)('primary %s', (primary) => {
  describe.each(paletteNames)('on the %s palette', (name) => {
    it.each(pairsFor(name, primary, null).map((p) => [p.label, p] as const))('%s', (_label, p) => {
      expect(contrast(p.fg, p.bg)).toBeGreaterThanOrEqual(p.min)
    })
  })
})

describe.each(EVENT_SECONDARY_COLORS)('secondary %s', (secondary) => {
  describe.each(paletteNames)('on the %s palette', (name) => {
    it.each(pairsFor(name, null, secondary).map((p) => [p.label, p] as const))(
      '%s',
      (_label, p) => {
        expect(contrast(p.fg, p.bg)).toBeGreaterThanOrEqual(p.min)
      },
    )
  })
})

describe.each(EVENT_BASE_COLORS)('base tone %s', (base) => {
  // The classic palette keeps its black and white: someone chose it.
  it.each(['classic light', 'classic dark'] as const)('leaves the %s palette alone', (name) => {
    // The preset's own variables are there; the app's tokens are not touched.
    const appTokens = (t: Tokens) => [...t].filter(([token]) => !token.startsWith('--event-base-'))
    expect(appTokens(dressed(name, 'blue', null, base))).toEqual(
      appTokens(dressed(name, 'blue', null)),
    )
  })

  describe.each(['default light', 'default dark'] as const)('on the %s palette', (name) => {
    it.each(pairsFor(name, null, null, base).map((p) => [p.label, p] as const))(
      '%s',
      (_label, p) => {
        expect(contrast(p.fg, p.bg)).toBeGreaterThanOrEqual(p.min)
      },
    )
  })
})

describe.each(paletteNames)('every pairing on the %s palette', (name) => {
  it('stays readable', () => {
    const failures: string[] = []
    for (const primary of [null, ...EVENT_PRIMARY_COLORS]) {
      for (const secondary of [null, ...EVENT_SECONDARY_COLORS]) {
        for (const base of [null, ...EVENT_BASE_COLORS]) {
          for (const p of pairsFor(name, primary, secondary, base)) {
            const ratio = contrast(p.fg, p.bg)
            if (ratio < p.min) {
              const look = `${primary} + ${secondary} on ${base}`
              failures.push(`${look}: ${p.label} ${ratio.toFixed(2)} < ${p.min}`)
            }
          }
        }
      }
    }
    expect(failures).toEqual([])
  })
})

/**
 * Own colours from all round the wheel, light to dark, grey to vivid, and a
 * few that are hard on purpose: pure yellow (too pale to read as text),
 * navy (too dark to fill under dark text), white, black.
 */
const OWN_COLOURS = [
  ...Array.from({ length: 24 }, (_, i) => i * 15).flatMap((h) =>
    [0.3, 0.6, 0.9].flatMap((l) => [0.04, 0.12, 0.25].map((c) => oklchToHex({ l, c, h }))),
  ),
  '#ffff00',
  '#fffde7',
  '#1e3a8a',
  '#ffffff',
  '#000000',
  '#808080',
  '#00ff00',
  '#ff00ff',
  '#1e6bb8',
]

describe.each(paletteNames)('own colours on the %s palette', (name) => {
  it('read as well as a preset, as main colour, second colour, base tone, and together', () => {
    const failures: string[] = []
    for (const hex of OWN_COLOURS) {
      const looks: [string | null, string | null, string | null][] = [
        [hex, null, null],
        [null, hex, null],
        [null, null, hex],
        [hex, hex, 'primary'],
        [hex, 'yellow', 'neutral'],
      ]
      for (const [primary, secondary, base] of looks) {
        for (const p of pairsFor(name, primary, secondary, base)) {
          const ratio = contrast(p.fg, p.bg)
          if (ratio < p.min) {
            const look = `${primary} + ${secondary} on ${base}`
            failures.push(`${look}: ${p.label} ${ratio.toFixed(2)} < ${p.min}`)
          }
        }
      }
    }
    expect(failures).toEqual([])
  })
})

describe('the surfaces an own colour is checked against', () => {
  // `custom-colour.ts` keeps its own copy, so it needs no stylesheet at runtime.
  const oklch = (value: string) => {
    const [l, c, h] = /^oklch\(([\d.]+) ([\d.]+) ([\d.]+)\)$/.exec(value)!.slice(1).map(Number)
    return { l, c, h }
  }
  const tokens = (palette: PaletteName, token: string) => oklch(PALETTES[palette].get(token)!)

  it("are the palettes' own", () => {
    expect(SURFACES.light).toEqual([
      tokens('default light', '--background'),
      tokens('default light', '--card'),
      tokens('default light', '--muted'),
      tokens('classic light', '--background'),
      tokens('classic light', '--muted'),
      tokens('classic light', '--sidebar'),
    ])
    expect(SURFACES.dark).toEqual([
      tokens('default dark', '--background'),
      tokens('default dark', '--card'),
      tokens('default dark', '--muted'),
      tokens('classic dark', '--background'),
      tokens('classic dark', '--muted'),
      tokens('classic dark', '--sidebar'),
    ])
  })
})

describe('the presets in index.css', () => {
  const inCss = (pattern: RegExp) =>
    [...css.matchAll(pattern)].map((m) => m[1]).sort((a, b) => a!.localeCompare(b!))

  it.each([
    ['primary', EVENT_PRIMARY_COLORS],
    ['secondary', EVENT_SECONDARY_COLORS],
  ] as const)(
    'are exactly the %s colours the app offers, each with a light and a dark set',
    (kind, offered) => {
      const sorted = [...offered].sort()
      expect(inCss(new RegExp(`^\\[data-event-${kind}='(\\w+)'\\] \\{`, 'gm'))).toEqual(sorted)
      expect(inCss(new RegExp(`^\\.dark\\[data-event-${kind}='(\\w+)'\\] \\{`, 'gm'))).toEqual(
        sorted,
      )
      expect(inCss(new RegExp(`^\\.dark \\[data-event-${kind}='(\\w+)'\\],$`, 'gm'))).toEqual(
        sorted,
      )
    },
  )

  it('are exactly the base tones the app offers', () => {
    expect(inCss(/^\[data-event-base='(\w+)'\] \{/gm)).toEqual([...EVENT_BASE_COLORS].sort())
  })

  it('give every base tone a hue and a strength, and neutral none', () => {
    for (const base of EVENT_BASE_COLORS) {
      const preset = rule(`[data-event-base='${base}']`)
      expect(preset.get('--event-base-hue'), base).toBeTruthy()
      expect(Number(preset.get('--event-base-chroma')), base).toBeGreaterThanOrEqual(0)
    }
    expect(rule(`[data-event-base='neutral']`).get('--event-base-chroma')).toBe('0')
    // The main colour's hue, and something sensible without one.
    expect(rule(`[data-event-base='primary']`).get('--event-base-hue')).toBe(
      'var(--event-primary-hue, 80)',
    )
  })

  it('give every primary a hue for the dark neutrals', () => {
    for (const primary of EVENT_PRIMARY_COLORS) {
      expect(rule(`[data-event-primary='${primary}']`).get('--event-primary-hue')).toMatch(/^\d+$/)
    }
  })

  it('hand the primary to the tokens that mean "the app\'s colour"', () => {
    expect(Object.fromEntries(rule(ON_PRIMARY))).toEqual({
      '--primary': 'var(--event-primary)',
      '--primary-foreground': 'var(--event-primary-foreground)',
      '--ring': 'var(--event-primary)',
      '--sidebar-primary': 'var(--event-primary)',
      '--sidebar-primary-foreground': 'var(--event-primary-foreground)',
      '--sidebar-ring': 'var(--event-primary)',
      '--hero': 'var(--event-primary-hero)',
      '--hero-foreground': 'var(--event-primary-hero-foreground)',
    })
  })

  it('hand the secondary to the secondary surfaces and the chip', () => {
    expect(Object.fromEntries(rule(ON_SECONDARY))).toEqual({
      '--secondary': 'var(--event-secondary-soft)',
      '--secondary-foreground': 'var(--event-secondary-soft-foreground)',
      '--accent': 'var(--event-secondary-soft)',
      '--accent-foreground': 'var(--event-secondary-soft-foreground)',
      '--sidebar-accent': 'var(--event-secondary-soft)',
      '--sidebar-accent-foreground': 'var(--event-secondary-soft-foreground)',
      '--hero-chip': 'var(--event-secondary)',
      '--hero-chip-foreground': 'var(--event-secondary-foreground)',
      '--hero-speck': 'var(--event-secondary)',
    })
    // Paler on the classic palette's near-white, for its grey text.
    expect(Object.fromEntries(rule(CLASSIC_LIGHT_SECONDARY))).toEqual({
      '--secondary': 'var(--event-secondary-pale)',
      '--accent': 'var(--event-secondary-pale)',
      '--sidebar-accent': 'var(--event-secondary-pale)',
    })
  })

  it("keep the dark neutrals' lightness and chroma, changing only the hue", () => {
    const lightnessAndChroma = (value: string) =>
      /^oklch\(\s*([\d.]+)\s+([\d.]+)\s/.exec(value)!.slice(1, 3).map(Number)
    const dark = rule('.dark')
    for (const [token, value] of [...rule(DARK_NEUTRALS), ...rule(DARK_SURFACES)]) {
      expect(value, token).toMatch(/var\(--event-primary-hue\)\)$/)
      expect(lightnessAndChroma(value), token).toEqual(lightnessAndChroma(dark.get(token)!))
    }
  })

  it("keep the palette's lightness and chroma under a base tone, scaling only the tint", () => {
    const toned = (value: string) =>
      /^oklch\(([\d.]+) calc\(([\d.]+) \* var\(--event-base-chroma\)\) var\(--event-base-hue\)\)$/
        .exec(value)!
        .slice(1, 3)
        .map(Number)
    const lightnessAndChroma = (value: string) =>
      /^oklch\(\s*([\d.]+)\s+([\d.]+)\s/.exec(value)!.slice(1, 3).map(Number)
    const light = PALETTES['default light']
    const dark = PALETTES['default dark']
    const sets: [string, Tokens][] = [
      [BASE_LIGHT, light],
      [BASE_LIGHT_SURFACES, light],
      [BASE_DARK, dark],
      [BASE_DARK_SURFACES, dark],
    ]
    for (const [selector, palette] of sets) {
      expect(rule(selector).size, selector).toBeGreaterThan(0)
      for (const [token, value] of rule(selector)) {
        expect(toned(value), `${selector} ${token}`).toEqual(
          lightnessAndChroma(palette.get(token)!),
        )
      }
    }
  })
})
