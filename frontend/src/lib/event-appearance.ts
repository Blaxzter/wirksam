import { isHexColour } from '@/lib/colour-math'
import { type ColourKind, registerCustomColour } from '@/lib/custom-colour'

/**
 * The colours an event can wear; see "Event colours" in index.css.
 *
 * The primary one (`events.primary_color`) is the app's colour: buttons,
 * links, the active navigation item, the hero panels. The secondary one
 * (`events.secondary_color`) fills the secondary buttons, the hover and
 * selected surfaces and the highlight chips. The base one
 * (`events.base_color`) is the tone of the background, cards and menu.
 *
 * Each is one of the presets below or an own colour, `#rrggbb`, which
 * `custom-colour.ts` turns into a preset at runtime.
 */

/**
 * In the order the picker shows them: round the colour wheel, grey last.
 *
 * The primary colour is also text on the page, so it has no yellow (one light
 * enough to be a fill is unreadable as text on cream) and no green (the app's
 * own already is). The secondary one is only ever a fill under dark text.
 */
export const EVENT_PRIMARY_COLORS = [
  'red',
  'orange',
  'teal',
  'blue',
  'violet',
  'pink',
  'slate',
] as const

export const EVENT_SECONDARY_COLORS = [
  'red',
  'orange',
  'yellow',
  'green',
  'teal',
  'blue',
  'violet',
  'pink',
  'slate',
] as const

/**
 * `primary` takes the main colour's hue (and means nothing without one),
 * `neutral` is grey; the rest round the colour wheel.
 */
export const EVENT_BASE_COLORS = [
  'primary',
  'neutral',
  'rose',
  'green',
  'teal',
  'blue',
  'violet',
] as const

export type EventPrimaryColor = (typeof EVENT_PRIMARY_COLORS)[number]
export type EventSecondaryColor = (typeof EVENT_SECONDARY_COLORS)[number]
export type EventBaseColor = (typeof EVENT_BASE_COLORS)[number]

const PRESETS: Record<ColourKind, readonly string[]> = {
  primary: EVENT_PRIMARY_COLORS,
  secondary: EVENT_SECONDARY_COLORS,
  base: EVENT_BASE_COLORS,
}

/**
 * What goes into `data-event-<kind>` for a stored colour: a preset's name, or
 * an own colour (registered as a preset on the way), or `undefined` for none
 * and for anything this build does not know.
 */
export function eventColourAttr(kind: ColourKind, value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  if (PRESETS[kind].includes(value)) return value
  if (isHexColour(value)) return registerCustomColour(kind, value)
  return undefined
}

export function isEventPrimaryColor(value: unknown): value is EventPrimaryColor {
  return typeof value === 'string' && (EVENT_PRIMARY_COLORS as readonly string[]).includes(value)
}

export function isEventSecondaryColor(value: unknown): value is EventSecondaryColor {
  return typeof value === 'string' && (EVENT_SECONDARY_COLORS as readonly string[]).includes(value)
}

export function isEventBaseColor(value: unknown): value is EventBaseColor {
  return typeof value === 'string' && (EVENT_BASE_COLORS as readonly string[]).includes(value)
}

export interface LogoSource {
  id: string
  logo_etag?: string | null
  logo_dark_etag?: string | null
  logo_dark_tile?: boolean | null
}

/**
 * The URL of an event's logo, or `null` when it has none.
 *
 * Served without a token (an `<img>` cannot send one), at a URL that changes
 * with every new logo, so the browser can cache it for good. `dark` is the
 * version for dark mode, which only counts beside the logo itself.
 */
export function eventLogoUrl(
  source: LogoSource | null | undefined,
  variant: 'light' | 'dark' = 'light',
): string | null {
  if (!source?.logo_etag) return null
  const base = `${import.meta.env.VITE_API_URL}/events/${source.id}/logo`
  if (variant === 'light') return `${base}?v=${source.logo_etag}`
  return source.logo_dark_etag ? `${base}/dark?v=${source.logo_dark_etag}` : null
}

/**
 * Whether dark mode puts the logo on a white tile; on unless the organisers
 * switched it off, since most logos are drawn for a light page.
 */
export function hasDarkTile(source: LogoSource | null | undefined): boolean {
  return source?.logo_dark_tile !== false
}

/**
 * At least this much wider than tall and a logo counts as a wordmark: it
 * carries the event's name itself, so the sidebar shows it on its own rather
 * than beside the name.
 */
export const WORDMARK_MIN_ASPECT = 2

/** Whether an event's logo is a wordmark; `false` without a logo or its size. */
export function isWordmark(
  source: { logo_width?: number | null; logo_height?: number | null } | null | undefined,
): boolean {
  const width = source?.logo_width
  const height = source?.logo_height
  if (!width || !height) return false
  return width / height >= WORDMARK_MIN_ASPECT
}

/** The first letter of an event's name, for the tile shown when it has no logo. */
export function eventInitial(name: string | null | undefined): string {
  const first = Array.from((name ?? '').trim())[0]
  return first ? first.toLocaleUpperCase() : '?'
}
