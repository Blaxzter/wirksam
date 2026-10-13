import type { Component } from 'vue'

import { CookingPot, Cross, DoorOpen, Info, MapPin, SquareParking, Toilet } from '@lucide/vue'

import type { LocationRead, VenueLocationStat, VenueMarkerRead } from '@/client/types.gen'

/**
 * Geometry and vocabulary for venue maps (#185).
 *
 * Everything here is pure so the pan/zoom composable and the map components
 * share one definition of what a view box is and where it may go.
 *
 * Coordinates come in two flavours:
 * - **normalised** (`0..1`), which is what the API stores per marker, so a
 *   replaced plan image keeps its pins;
 * - **image units** (`0..W`, `0..H`), the plan's pixel size after the server
 *   resized it. The SVG's user space is image units, so `<image>` sits at
 *   `0 0 W H` and a marker at `(x·W, y·H)`.
 */

export type MarkerKind = VenueMarkerRead['kind']

/**
 * The URL of a plan's picture, or `null` when it has none yet.
 *
 * The etag rides along as `?v=` so a replaced image gets a new URL and the
 * browser cache never serves the old one. The endpoint is member-only, so load
 * it through `useAuthedImage`, not a plain `<img src>`.
 */
export function planImageUrl(
  plan: { id: string; image_etag?: string | null } | null | undefined,
): string | null {
  if (!plan?.image_etag) return null
  return `${import.meta.env.VITE_API_URL}/venue-plans/${plan.id}/image?v=${plan.image_etag}`
}

/** Every marker kind, in the order pickers list them. */
export const MARKER_KINDS = [
  'location',
  'entrance',
  'info_desk',
  'first_aid',
  'toilets',
  'parking',
  'kitchen',
] as const satisfies readonly MarkerKind[]

/** The kinds that are not tied to a location row (a marker with its own label). */
export const GENERIC_MARKER_KINDS = MARKER_KINDS.filter(
  (kind): kind is Exclude<MarkerKind, 'location'> => kind !== 'location',
)

const MARKER_ICONS: Record<MarkerKind, Component> = {
  location: MapPin,
  entrance: DoorOpen,
  info_desk: Info,
  first_aid: Cross,
  toilets: Toilet,
  parking: SquareParking,
  kitchen: CookingPot,
}

/** The lucide icon drawn inside a marker. Unknown kinds fall back to a pin. */
export function markerIcon(kind: string): Component {
  return MARKER_ICONS[kind as MarkerKind] ?? MapPin
}

/**
 * The i18n key naming a marker kind (`venueMap.markerKinds.*`). The API uses
 * snake_case, the locale files camelCase.
 */
export function markerKindLabelKey(kind: string): string {
  const camel = kind.replace(/_([a-z])/g, (_m, c: string) => c.toUpperCase())
  return `venueMap.markerKinds.${camel}`
}

/**
 * How well a place is staffed on the day the map shows.
 *
 * - `full`: every slot of that day's shifts there is booked;
 * - `partial`: at least half of them are;
 * - `short`: fewer than half;
 * - `none`: no shifts there that day (the API leaves such a place out of
 *   `location_stats`, so a missing entry means `none`).
 */
export type StaffingStatus = 'full' | 'partial' | 'short' | 'none'

/** The statuses a legend lists, most to least staffed. */
export const STAFFING_LEGEND = ['full', 'partial', 'short'] as const satisfies StaffingStatus[]

/** Share of booked slots from which a place counts as partly rather than under-staffed. */
export const PARTIAL_THRESHOLD = 0.5

export function staffingStatus(
  stat: { booked: number; capacity: number } | null | undefined,
): StaffingStatus {
  if (!stat || !(stat.capacity > 0)) return 'none'
  if (stat.booked >= stat.capacity) return 'full'
  return stat.booked / stat.capacity >= PARTIAL_THRESHOLD ? 'partial' : 'short'
}

/** The i18n key naming a staffing status (`venueMap.staffing.*`). */
export function staffingLabelKey(status: StaffingStatus): string {
  return `venueMap.staffing.${status}`
}

/**
 * Literal class names per status, so Tailwind's scanner emits them. The
 * colours are theme tokens (`--staff-*` in `index.css`) with a light and a
 * dark value each.
 */
export const STAFFING_CLASSES: Record<
  StaffingStatus,
  { fill: string; stroke: string; bg: string; text: string; chip: string }
> = {
  full: {
    fill: 'fill-staff-full',
    stroke: 'stroke-staff-full',
    bg: 'bg-staff-full',
    text: 'text-staff-full',
    chip: 'border-staff-full/40 bg-staff-full/10 text-staff-full',
  },
  partial: {
    fill: 'fill-staff-partial',
    stroke: 'stroke-staff-partial',
    bg: 'bg-staff-partial',
    text: 'text-staff-partial',
    chip: 'border-staff-partial/50 bg-staff-partial/10 text-foreground',
  },
  short: {
    fill: 'fill-staff-short',
    stroke: 'stroke-staff-short',
    bg: 'bg-staff-short',
    text: 'text-staff-short',
    chip: 'border-staff-short/40 bg-staff-short/10 text-staff-short',
  },
  none: {
    fill: 'fill-staff-none',
    stroke: 'stroke-staff-none',
    bg: 'bg-staff-none',
    text: 'text-muted-foreground',
    chip: 'border-border bg-muted text-muted-foreground',
  },
}

/** One row of the map's list of places (`VenuePlaceOverview`). */
export type PlaceOverviewItem = {
  location: LocationRead
  badge: number
  stat: VenueLocationStat | null
  /** Has a pin on some plan; a place without one cannot be shown on the map. */
  pinned: boolean
  /** The viewer has a shift there that day. */
  mine: boolean
}

/**
 * A rough width (CSS px) of `text` set at `fontSize` px, for laying out a
 * marker pill before the browser has measured it (and in tests, where there is
 * no layout). Errs on the wide side so a pill is never too short to hold its
 * text.
 */
export function estimateTextWidth(text: string, fontSize: number): number {
  let em = 0
  for (const ch of text) {
    if (/[ilj.,:;'|!]/.test(ch)) em += 0.3
    else if (/[mwMW]/.test(ch)) em += 0.85
    else if (/[A-ZÄÖÜ0-9]/.test(ch)) em += 0.66
    else if (ch === ' ') em += 0.3
    else em += 0.56
  }
  return Math.ceil(em * fontSize)
}

/**
 * The one location a task happens at, for its mini-map: the location every
 * shift shares, or the task's own while it has no shifts. A shift without a
 * location, or two different ones, means there is no single place: `null`.
 * Task details and the print view both use this, so they show the same map.
 */
export function sharedLocationId(
  shifts: readonly { location_id?: string | null }[],
  taskLocationId: string | null | undefined,
): string | null {
  if (shifts.length === 0) return taskLocationId ?? null
  const first = shifts[0]!.location_id ?? null
  if (!first) return null
  return shifts.every((s) => s.location_id === first) ? first : null
}

export function clamp01(value: number): number {
  if (Number.isNaN(value)) return 0
  return Math.min(1, Math.max(0, value))
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

/** An SVG view box in image units. */
export type ViewBox = { x: number; y: number; w: number; h: number }

export type Point = { x: number; y: number }

/** The view box that shows the whole image. */
export function fitViewBox(W: number, H: number): ViewBox {
  return { x: 0, y: 0, w: W, h: H }
}

/** The share of the image that must stay on screen while panning. */
const MIN_VISIBLE = 0.1

/**
 * Move the view box by `(dx, dy)` image units.
 *
 * Clamped so at least 10% of the image stays inside the view on each axis —
 * the plan can be dragged aside to look at an edge, but never lost.
 */
export function panBy(vb: ViewBox, dx: number, dy: number, W: number, H: number): ViewBox {
  return {
    ...vb,
    x: clamp(vb.x + dx, MIN_VISIBLE * W - vb.w, (1 - MIN_VISIBLE) * W),
    y: clamp(vb.y + dy, MIN_VISIBLE * H - vb.h, (1 - MIN_VISIBLE) * H),
  }
}

/**
 * Zoom by `factor` (> 1 zooms in) keeping the image point `(px, py)` fixed on
 * screen — the cursor for a wheel, the midpoint for a pinch.
 *
 * The width is clamped to `[minW, maxW]`; the height follows the current
 * aspect ratio so the box never distorts. The result is pan-clamped.
 */
export function zoomAt(
  vb: ViewBox,
  factor: number,
  px: number,
  py: number,
  W: number,
  H: number,
  minW: number,
  maxW: number,
): ViewBox {
  if (!(factor > 0) || !(vb.w > 0)) return vb
  const w = clamp(vb.w / factor, minW, maxW)
  const ratio = w / vb.w
  const next = {
    x: px - (px - vb.x) * ratio,
    y: py - (py - vb.y) * ratio,
    w,
    h: vb.h * ratio,
  }
  return panBy(next, 0, 0, W, H)
}

/** Image units → normalised coordinates, clamped to the image. */
export function toNormalised(point: Point, W: number, H: number): Point {
  return {
    x: W > 0 ? clamp01(point.x / W) : 0,
    y: H > 0 ? clamp01(point.y / H) : 0,
  }
}

/**
 * The view box for a mini-map around the normalised point `(x, y)`.
 *
 * It spans `fraction` of the image width at the given `aspect` (the mini-map
 * box is 16:9), shrinks to fit when the image is too small for that, and is
 * shifted rather than centred near an edge so it never shows empty space
 * outside the image.
 */
export function cropAround(
  x: number,
  y: number,
  W: number,
  H: number,
  fraction = 0.35,
  aspect = 16 / 9,
): ViewBox {
  let w = W * fraction
  let h = w / aspect
  if (h > H) {
    h = H
    w = h * aspect
  }
  if (w > W) {
    w = W
    h = w / aspect
  }
  const cx = clamp01(x) * W
  const cy = clamp01(y) * H
  return {
    x: clamp(cx - w / 2, 0, W - w),
    y: clamp(cy - h / 2, 0, H - h),
    w,
    h,
  }
}

/** Serialise a view box for the `viewBox` attribute. */
export function viewBoxToString(vb: ViewBox): string {
  return `${vb.x} ${vb.y} ${vb.w} ${vb.h}`
}

/**
 * Image units per CSS pixel for an SVG showing `vb` in a `clientWidth` ×
 * `clientHeight` box with the default `preserveAspectRatio="xMidYMid meet"`.
 *
 * Multiply a marker by this to draw it at a constant screen size whatever the
 * zoom level. Falls back to `1` before the element has been laid out.
 */
export function unitsPerPixel(vb: ViewBox, clientWidth: number, clientHeight: number): number {
  const sx = clientWidth > 0 ? vb.w / clientWidth : 0
  const sy = clientHeight > 0 ? vb.h / clientHeight : 0
  const scale = Math.max(sx, sy)
  return scale > 0 ? scale : 1
}

/** The part of a `DOMRect` that {@link clientToImage} needs. */
export type ClientRect = { left: number; top: number; width: number; height: number }

/**
 * A screen (client) point → image units, for an SVG showing `vb` inside
 * `rect` with `preserveAspectRatio="xMidYMid meet"`.
 *
 * This is what `svg.getScreenCTM().inverse()` computes, but from the view box
 * we are about to render rather than the one the browser last painted — during
 * a pinch several pointer events can land before the next frame, and the CTM
 * would still describe the old zoom.
 */
export function clientToImage(
  vb: ViewBox,
  rect: ClientRect,
  clientX: number,
  clientY: number,
): Point {
  const k = unitsPerPixel(vb, rect.width, rect.height)
  // `meet` centres the scaled box, leaving equal bars on the longer side.
  const offsetX = rect.width > 0 ? (rect.width - vb.w / k) / 2 : 0
  const offsetY = rect.height > 0 ? (rect.height - vb.h / k) / 2 : 0
  return {
    x: vb.x + (clientX - rect.left - offsetX) * k,
    y: vb.y + (clientY - rect.top - offsetY) * k,
  }
}
