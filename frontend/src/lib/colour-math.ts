/**
 * Colour arithmetic for the event colours: OKLCH (what `index.css` is written
 * in) to and from sRGB hex, keeping a colour inside what a screen can show, and
 * WCAG 2.x contrast. Shared by the app, which derives an event's own colours
 * at runtime (`custom-colour.ts`), and by the specs that recompute the
 * stylesheet's contrast, so both measure the same way.
 *
 * Formulas from Björn Ottosson's OKLab; contrast as WCAG defines it, on
 * linear-light sRGB.
 */

/** Linear-light sRGB, each channel 0 to 1. */
export type Rgb = [number, number, number]

/** Lightness 0 to 1, chroma from 0, hue in degrees. */
export interface Oklch {
  l: number
  c: number
  h: number
}

/** OKLCH to linear sRGB, unclamped: a channel outside 0..1 is out of gamut. */
export function oklchToLinearRgbRaw(L: number, C: number, h: number): Rgb {
  const a = C * Math.cos((h * Math.PI) / 180)
  const b = C * Math.sin((h * Math.PI) / 180)
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b
  const s_ = L - 0.0894841775 * a - 1.291485548 * b
  const [l, m, s] = [l_ ** 3, m_ ** 3, s_ ** 3]
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ]
}

const clamp01 = (x: number) => Math.min(1, Math.max(0, x))

/** OKLCH to linear sRGB, clamped to the gamut, as a browser paints a token. */
export function oklchToLinearRgb(L: number, C: number, h: number): Rgb {
  return oklchToLinearRgbRaw(L, C, h).map(clamp01) as Rgb
}

const GAMUT_EPSILON = 1e-4

function inGamut({ l, c, h }: Oklch): boolean {
  return oklchToLinearRgbRaw(l, c, h).every((x) => x >= -GAMUT_EPSILON && x <= 1 + GAMUT_EPSILON)
}

/**
 * The colour at this lightness and hue with as much of its chroma as a screen
 * can show: a vivid blue made very light or very dark has to give some up.
 */
export function fitToGamut(colour: Oklch): Oklch {
  if (inGamut(colour)) return colour
  let lo = 0
  let hi = colour.c
  for (let i = 0; i < 24; i++) {
    const mid = (lo + hi) / 2
    if (inGamut({ ...colour, c: mid })) lo = mid
    else hi = mid
  }
  return { ...colour, c: lo }
}

/** The colour as a screen shows it, in linear-light sRGB. */
export function rgbOf(colour: Oklch): Rgb {
  const { l, c, h } = fitToGamut(colour)
  return oklchToLinearRgb(l, c, h)
}

// The matrix output is already linear, so no gamma step before luminance.
const luminance = (rgb: Rgb) => 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]

/** WCAG 2.x contrast ratio, 1 to 21. */
export function contrast(a: Rgb, b: Rgb): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((p, q) => q - p) as [number, number]
  return (hi + 0.05) / (lo + 0.05)
}

const encode = (x: number) => (x <= 0.0031308 ? 12.92 * x : 1.055 * x ** (1 / 2.4) - 0.055)
const decode = (x: number) => (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4)

/**
 * `alpha` of `fg` over `bg` (a Tailwind `/15` tint), composited as the browser
 * paints it: in gamma-encoded sRGB, not in linear light.
 */
export function over(fg: Rgb, alpha: number, bg: Rgb): Rgb {
  return [0, 1, 2].map((i) => decode(alpha * encode(fg[i]!) + (1 - alpha) * encode(bg[i]!))) as Rgb
}

const HEX = /^#([0-9a-f]{6})$/i

export function isHexColour(value: unknown): value is string {
  return typeof value === 'string' && HEX.test(value)
}

/** `#1e6bb8` to OKLCH. Hue is 0 for a grey, which has none. */
export function hexToOklch(hex: string): Oklch {
  const match = HEX.exec(hex)
  if (!match) throw new Error(`not a colour: ${hex}`)
  const n = parseInt(match[1]!, 16)
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((x) => decode(x / 255)) as Rgb
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s
  const c = Math.hypot(A, B)
  const h = c < 1e-4 ? 0 : (Math.atan2(B, A) * 180) / Math.PI
  return { l: L, c, h: h < 0 ? h + 360 : h }
}

/** OKLCH to `#rrggbb`, fitted into the gamut first. */
export function oklchToHex(colour: Oklch): string {
  return (
    '#' +
    rgbOf(colour)
      .map((x) => Math.round(clamp01(encode(x)) * 255))
      .map((x) => x.toString(16).padStart(2, '0'))
      .join('')
  )
}

const round = (x: number, digits: number) => Number(x.toFixed(digits))

/** The colour as a CSS value, fitted into the gamut: `oklch(0.4712 0.1401 258.12)`. */
export function oklchCss(colour: Oklch): string {
  const { l, c, h } = fitToGamut(colour)
  return `oklch(${round(l, 4)} ${round(c, 4)} ${round(h, 2)})`
}
