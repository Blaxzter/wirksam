import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

// Read from disk: Vitest hands CSS imports (`?raw` included) back empty.
const css = readFileSync(new URL('../../index.css', import.meta.url), 'utf8')

/**
 * WCAG 2.x contrast of the venue map's colour tokens, recomputed from
 * `index.css` itself so a retuned colour cannot quietly make the map
 * unreadable (#185: "the colours are hard to read, especially in dark mode").
 *
 * Text pairs need 4.5:1, non-text indicators (a pill's status outline, a
 * highlight ring) 3:1. Both themes are checked, plus the `.map-light` set a
 * picture plan uses in dark mode, which must equal the light one.
 */

type Rgb = [number, number, number]

/** oklch → linear sRGB, clamped to the gamut. */
function oklchToLinearRgb(L: number, C: number, h: number): Rgb {
  const a = C * Math.cos((h * Math.PI) / 180)
  const b = C * Math.sin((h * Math.PI) / 180)
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b
  const s_ = L - 0.0894841775 * a - 1.291485548 * b
  const [l, m, s] = [l_ ** 3, m_ ** 3, s_ ** 3]
  const clamp = (x: number) => Math.min(1, Math.max(0, x))
  return [
    clamp(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
    clamp(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
    clamp(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s),
  ]
}

// The matrix output is already linear, so no gamma step before luminance.
const luminance = (c: Rgb) => 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

function contrast(a: Rgb, b: Rgb): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((p, q) => q - p) as [number, number]
  return (hi + 0.05) / (lo + 0.05)
}

const encode = (x: number) => (x <= 0.0031308 ? 12.92 * x : 1.055 * x ** (1 / 2.4) - 0.055)
const decode = (x: number) => (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4)

/**
 * `alpha` of `fg` over `bg` (a Tailwind `/75` or `/12` colour), composited as
 * the browser paints it: in gamma-encoded sRGB, not in linear light. Linear
 * blending would understate a translucent text colour on a dark card.
 */
function over(fg: Rgb, alpha: number, bg: Rgb): Rgb {
  return [0, 1, 2].map((i) => decode(alpha * encode(fg[i]!) + (1 - alpha) * encode(bg[i]!))) as Rgb
}

type Tokens = Map<string, string>

/** Every `--name: value;` of every top-level rule whose selector list matches. */
function declarations(selector: (sel: string) => boolean): Tokens {
  const out: Tokens = new Map()
  // Top-level rules only (a rule inside `@media print` follows a `{`, not a
  // `}`): comments stripped, then `selector { body }` with no nesting.
  const source = css.replace(/\/\*[\s\S]*?\*\//g, '')
  const rule = /(?<=^|\})\s*([^{}@]+?)\s*\{([^{}]*)\}/g
  for (const match of source.matchAll(rule)) {
    const selectors = match[1]!.split(',').map((s) => s.trim())
    if (!selectors.some(selector)) continue
    for (const decl of match[2]!.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
      out.set(decl[1]!, decl[2]!.trim())
    }
  }
  return out
}

const light = declarations((s) => s === ':root')
const dark = new Map([...light, ...declarations((s) => s === '.dark')])
const mapLight = declarations((s) => s === '.map-light')

function colour(tokens: Tokens, name: string, seen: string[] = []): Rgb {
  const raw = tokens.get(name)
  if (!raw) throw new Error(`${name} is not declared`)
  const ref = /^var\((--[\w-]+)\)$/.exec(raw)
  if (ref) {
    if (seen.includes(ref[1]!)) throw new Error(`cycle at ${name}`)
    return colour(tokens, ref[1]!, [...seen, name])
  }
  const m = /^oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)$/.exec(raw)
  if (!m) throw new Error(`${name}: cannot parse "${raw}"`)
  return oklchToLinearRgb(Number(m[1]), Number(m[2]), Number(m[3]))
}

const STYLES = [
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
  'hedge',
  'fence',
  'sand',
] as const

const THEMES = { light, dark } as const

type Pair = { label: string; fg: Rgb; bg: Rgb; min: number }

function pairs(t: Tokens): Pair[] {
  const c = (name: string) => colour(t, name)
  const TEXT = 4.5
  const UI = 3
  const list: Pair[] = []
  for (const style of STYLES) {
    const ink = c(`--map-shape-${style}-ink`)
    list.push({
      label: `${style} ink on its fill`,
      fg: ink,
      bg: c(`--map-shape-${style}-fill`),
      min: TEXT,
    })
    // A free label sits on the ground; a wall label uses the map ink instead.
    if (style !== 'wall') {
      list.push({ label: `${style} ink on the ground`, fg: ink, bg: c('--map-canvas'), min: TEXT })
    }
  }
  list.push(
    { label: 'map ink on the ground', fg: c('--map-ink'), bg: c('--map-canvas'), min: TEXT },
    {
      label: 'soft map ink on the ground',
      fg: c('--map-ink-soft'),
      bg: c('--map-canvas'),
      min: TEXT,
    },
    { label: 'pill name', fg: c('--map-pill-ink'), bg: c('--map-pill'), min: TEXT },
    { label: 'pill count', fg: c('--map-pill-ink-soft'), bg: c('--map-pill'), min: TEXT },
    { label: 'highlight on the ground', fg: c('--map-highlight'), bg: c('--map-canvas'), min: UI },
    { label: 'selection on the ground', fg: c('--map-select'), bg: c('--map-canvas'), min: UI },
    {
      label: 'side panel sub-label (foreground/75 on card)',
      fg: over(c('--foreground'), 0.75, c('--card')),
      bg: c('--card'),
      min: TEXT,
    },
  )
  for (const status of ['full', 'partial', 'short', 'none'] as const) {
    list.push(
      {
        label: `${status}: pill text on the status fill`,
        fg: c('--staff-foreground'),
        bg: c(`--staff-${status}`),
        min: TEXT,
      },
      {
        label: `${status}: status outline on the pill`,
        fg: c(`--staff-${status}`),
        bg: c('--map-pill'),
        min: UI,
      },
    )
    if (status !== 'none') {
      const chip = over(c(`--staff-${status}`), 0.12, c('--card'))
      list.push({
        label: `${status}: chip text on its tint`,
        fg: c(`--staff-${status}-ink`),
        bg: chip,
        min: TEXT,
      })
    }
  }
  return list
}

describe.each(Object.entries(THEMES))('venue map contrast, %s', (_name, tokens) => {
  it.each(pairs(tokens).map((p) => [p.label, p] as const))('%s', (_label, p) => {
    expect(contrast(p.fg, p.bg)).toBeGreaterThanOrEqual(p.min)
  })
})

describe('the .map-light set', () => {
  it('repeats every light map token with the same value', () => {
    const mapNames = [...light.keys()].filter((k) => /^--(map|staff)-/.test(k))
    expect(mapNames.length).toBeGreaterThan(40)
    for (const name of mapNames) expect([name, mapLight.get(name)]).toEqual([name, light.get(name)])
  })

  it('gives dark mode its own value for every map token', () => {
    // `transparent` (a style without an outline) and the shared muted ink are theme-free.
    const themed = [...mapLight.keys()].filter(
      (k) => k !== '--staff-none-ink' && light.get(k) !== 'transparent',
    )
    for (const name of themed) {
      expect([name, dark.get(name) !== light.get(name)]).toEqual([name, true])
    }
  })
})

describe('the decoration tokens', () => {
  // Decoration is no indicator, so it is not paired; it only has to parse, so
  // a typo cannot silently drop a tree's colour.
  const names = (t: Tokens) => [...t.keys()].filter((k) => k.startsWith('--map-decor-'))

  it.each(Object.entries(THEMES))('parse in %s', (_name, tokens) => {
    expect(names(tokens).length).toBeGreaterThanOrEqual(17)
    for (const name of names(tokens)) {
      if (name === '--map-decor-shadow') {
        expect(tokens.get(name)).toMatch(/^rgb\(\s*[\d.]+\s+[\d.]+\s+[\d.]+\s*\/\s*[\d.]+\s*\)$/)
      } else {
        expect(() => colour(tokens, name)).not.toThrow()
      }
    }
  })
})

describe('the contrast maths', () => {
  it('matches known values', () => {
    const white = oklchToLinearRgb(1, 0, 0)
    const black = oklchToLinearRgb(0, 0, 0)
    expect(contrast(white, black)).toBeCloseTo(21, 1)
    expect(contrast(white, white)).toBe(1)
  })

  it('reports unknown and malformed tokens', () => {
    const t: Tokens = new Map([
      ['--a', 'var(--b)'],
      ['--b', 'var(--a)'],
      ['--c', 'red'],
    ])
    expect(() => colour(t, '--x')).toThrow('not declared')
    expect(() => colour(t, '--a')).toThrow('cycle')
    expect(() => colour(t, '--c')).toThrow('cannot parse')
  })
})
