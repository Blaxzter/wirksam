import {
  type Oklch,
  contrast,
  fitToGamut,
  hexToOklch,
  isHexColour,
  oklchCss,
  oklchToHex,
  over,
  rgbOf,
} from '@/lib/colour-math'

/**
 * An event's own colour (`#1e6bb8`) in place of a preset: the club's colour.
 *
 * The organisers pick any colour and the app works out the rest, the way the
 * presets in `index.css` were worked out by hand. The hue stays theirs; the
 * lightness moves only as far as WCAG AA (4.5:1) needs, separately for light
 * and dark mode, and the text on it goes white or dark, whichever reads. So an
 * own colour is as readable as a preset, and the organisers see what was
 * changed (`report`).
 *
 * The result is a preset made at runtime: the same variables under
 * `[data-event-primary='#1e6bb8']` and its `.dark` twin, put in a `<style>` the
 * first time the colour is needed (`registerCustomColour`). From there the
 * hand-over rules in `index.css` treat it like any other.
 *
 * - primary: the colour as text on every light surface of both palettes (and
 *   over its own `/15` tint), white or dark text on it; in dark mode a lighter
 *   version, as text on every dark surface.
 * - secondary: a fill under dark text, so as light as that needs; its soft and
 *   pale surfaces at the presets' lightness, in its hue.
 * - base: the hue only, at the palette's lightness, with as much tint as the
 *   colour has (a grey gives plain grey).
 */

export type ColourKind = 'primary' | 'secondary' | 'base'

/** AA for text, with a little to spare for the hue a base tone gives a surface. */
export const TARGET = 4.6

/**
 * The surfaces text sits on, light and dark, in both palettes (see `:root`,
 * `.dark`, `.palette-classic` and `.palette-classic.dark` in index.css; the
 * contrast spec checks these stay in step). An own colour has to read on all.
 */
export const SURFACES = {
  light: [
    { l: 0.945, c: 0.018, h: 80 }, // background
    { l: 0.965, c: 0.014, h: 80 }, // card
    { l: 0.91, c: 0.022, h: 78 }, // muted, sidebar
    { l: 1, c: 0, h: 0 }, // classic background, card
    { l: 0.97, c: 0, h: 0 }, // classic muted
    { l: 0.985, c: 0, h: 0 }, // classic sidebar
  ],
  dark: [
    { l: 0.17, c: 0.01, h: 155 }, // background
    { l: 0.21, c: 0.012, h: 155 }, // card, sidebar
    { l: 0.25, c: 0.012, h: 155 }, // muted
    { l: 0.145, c: 0, h: 0 }, // classic background, card
    { l: 0.269, c: 0, h: 0 }, // classic muted
    { l: 0.205, c: 0, h: 0 }, // classic sidebar
  ],
} as const satisfies Record<'light' | 'dark', readonly Oklch[]>

type Mode = keyof typeof SURFACES

/** How well a colour reads as text on every surface of a mode, also over its own tint. */
function asText(colour: Oklch, mode: Mode): number {
  const fg = rgbOf(colour)
  return Math.min(
    ...SURFACES[mode].flatMap((surface) => {
      const bg = rgbOf(surface)
      return [contrast(fg, bg), contrast(fg, over(fg, 0.15, bg))]
    }),
  )
}

/** How well `text` reads on `fill`. */
const textOn = (text: Oklch, fill: Oklch) => contrast(rgbOf(text), rgbOf(fill))

/**
 * The colour at the lightness nearest its own that passes, searching darker
 * (`down`) or lighter (`up`). The hue and as much chroma as fits stay.
 */
function nearestPassing(colour: Oklch, passes: (c: Oklch) => boolean, way: 'up' | 'down'): Oklch {
  const at = (l: number) => fitToGamut({ ...colour, l })
  if (passes(at(colour.l))) return at(colour.l)
  // `good` always passes, `bad` never does; the answer lies between.
  let good = way === 'down' ? 0 : 1
  let bad = colour.l
  for (let i = 0; i < 30; i++) {
    const mid = (good + bad) / 2
    if (passes(at(mid))) good = mid
    else bad = mid
  }
  return at(good)
}

/** What the organisers' colour became in one mode. */
export interface ModeReport {
  /** The colour used, as hex. */
  used: string
  /** How well it reads where it is checked (as text for a main colour, under text for a second). */
  ratio: number
  /** The same for the colour as it was picked. */
  originalRatio: number
  /** Whether the lightness had to move. */
  adjusted: boolean
}

export interface CustomColour {
  kind: ColourKind
  /** The colour as picked, lower case. */
  hex: string
  /** The rules that make it a preset, for a `<style>`. */
  css: string
  /** Per mode; none for a base tone, which only lends its hue. */
  report: { light: ModeReport; dark: ModeReport } | null
}

const css = (vars: Record<string, string | number>) =>
  Object.entries(vars)
    .map(([name, value]) => `  --${name}: ${value};`)
    .join('\n')

function rules(attr: string, hex: string, light: string, dark?: string): string {
  const own = `[${attr}='${hex}']`
  const base = `${own} {\n${light}\n}`
  return dark ? `${base}\n.dark ${own},\n.dark${own} {\n${dark}\n}` : base
}

function report(
  original: Oklch,
  used: Oklch,
  ratio: (c: Oklch) => number,
  hex: string,
): ModeReport {
  const adjusted = Math.abs(used.l - original.l) > 0.002
  return {
    used: adjusted ? oklchToHex(used) : hex,
    ratio: ratio(used),
    originalRatio: ratio(original),
    adjusted,
  }
}

function primary(hex: string, picked: Oklch): CustomColour {
  const { h } = picked
  // Pure white: the light version is checked against the classic palette's
  // white page, so text in exactly that white is sure to read on it.
  const white = { l: 1, c: 0, h }
  const ink = { l: 0.17, c: 0.01, h }
  // Light: as text on pale surfaces, so dark enough; white text on it then reads too.
  const light = nearestPassing(picked, (c) => asText(c, 'light') >= TARGET, 'down')
  // Dark: as text on dark surfaces, so light enough, with dark text on it.
  const dark = nearestPassing(picked, (c) => asText(c, 'dark') >= TARGET, 'up')
  const hero = fitToGamut({ l: 0.32, c: Math.min(picked.c, 0.07), h })
  return {
    kind: 'primary',
    hex,
    css: rules(
      'data-event-primary',
      hex,
      css({
        'event-primary': oklchCss(light),
        'event-primary-foreground': oklchCss(white),
        'event-primary-hero': oklchCss(light),
        'event-primary-hero-foreground': oklchCss(white),
        'event-primary-hue': Number(h.toFixed(2)),
      }),
      css({
        'event-primary': oklchCss(dark),
        'event-primary-foreground': oklchCss(ink),
        'event-primary-hero': oklchCss(hero),
        'event-primary-hero-foreground': oklchCss({ l: 0.95, c: 0.01, h }),
      }),
    ),
    report: {
      light: report(picked, light, (c) => asText(c, 'light'), hex),
      dark: report(picked, dark, (c) => asText(c, 'dark'), hex),
    },
  }
}

function secondary(hex: string, picked: Oklch): CustomColour {
  const { h, c } = picked
  const lightInk = { l: 0.25, c: 0.03, h }
  const darkInk = { l: 0.17, c: 0.01, h }
  // A fill under dark text in both modes, so light enough for it.
  const light = nearestPassing(picked, (x) => textOn(lightInk, x) >= TARGET, 'up')
  const dark = nearestPassing(picked, (x) => textOn(darkInk, x) >= TARGET, 'up')
  return {
    kind: 'secondary',
    hex,
    css: rules(
      'data-event-secondary',
      hex,
      css({
        'event-secondary': oklchCss(light),
        'event-secondary-foreground': oklchCss(lightInk),
        'event-secondary-soft': oklchCss({ l: 0.925, c: Math.min(c, 0.05), h }),
        'event-secondary-soft-foreground': oklchCss({ l: 0.27, c: 0.02, h }),
        'event-secondary-pale': oklchCss({ l: 0.98, c: Math.min(c, 0.025), h }),
      }),
      css({
        'event-secondary': oklchCss(dark),
        'event-secondary-foreground': oklchCss(darkInk),
        'event-secondary-soft': oklchCss({ l: 0.31, c: Math.min(c, 0.05), h }),
        'event-secondary-soft-foreground': oklchCss({ l: 0.93, c: 0.01, h }),
      }),
    ),
    report: {
      light: report(picked, light, (x) => textOn(lightInk, x), hex),
      dark: report(picked, dark, (x) => textOn(darkInk, x), hex),
    },
  }
}

/**
 * How strongly a base tone in this colour tints the surfaces, on the scale of
 * the presets (1 is the cream's own tint): a grey gives none, a vivid colour
 * as much as the strongest preset.
 */
export function baseStrength(picked: Oklch): number {
  if (picked.c < 0.015) return 0
  return Number(Math.min(1.5, Math.max(0.5, picked.c / 0.09)).toFixed(2))
}

function base(hex: string, picked: Oklch): CustomColour {
  return {
    kind: 'base',
    hex,
    css: rules(
      'data-event-base',
      hex,
      css({
        'event-base-hue': Number(picked.h.toFixed(2)),
        'event-base-chroma': baseStrength(picked),
      }),
    ),
    report: null,
  }
}

const made = new Map<string, CustomColour>()

/** An own colour of one kind, worked out once and kept. */
export function customColour(kind: ColourKind, value: string): CustomColour {
  if (!isHexColour(value)) throw new Error(`not a colour: ${value}`)
  const hex = value.toLowerCase()
  const key = `${kind}:${hex}`
  let colour = made.get(key)
  if (!colour) {
    const picked = hexToOklch(hex)
    colour = (kind === 'primary' ? primary : kind === 'secondary' ? secondary : base)(hex, picked)
    made.set(key, colour)
  }
  return colour
}

const STYLE_ID = 'event-custom-colours'
const registered = new Set<string>()

/**
 * Make an own colour usable as `data-event-<kind>`: its rules go into one
 * `<style>` the first time it is needed. Answers the attribute value. Without
 * a document (the prerender) there is nothing to put it in, and nothing that
 * would show it either.
 */
export function registerCustomColour(kind: ColourKind, value: string): string {
  const colour = customColour(kind, value)
  const key = `${kind}:${colour.hex}`
  if (typeof document !== 'undefined' && !registered.has(key)) {
    let style = document.getElementById(STYLE_ID)
    if (!style) {
      style = document.createElement('style')
      style.id = STYLE_ID
      document.head.append(style)
    }
    style.append(`${colour.css}\n`)
    registered.add(key)
  }
  return colour.hex
}
