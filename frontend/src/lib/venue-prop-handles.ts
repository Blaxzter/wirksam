import { ROTATION_STEP, clampPropScale, normaliseRotation } from '@/lib/venue-decor'

/**
 * The geometry of the on-map grips of a selected decoration: the round
 * rotate grip on a stalk above the glyph and the corner grip that resizes it.
 * Everything here is in plan units (y grows downwards, like the SVG), and an
 * angle is in degrees clockwise from "up" — the same sense as a prop's
 * `rotation`, so a grip at `rotation` points where the glyph's top points.
 */

export type XY = { x: number; y: number }

/** The resize grip sits this far round the ring from the rotate grip (bottom right). */
export const RESIZE_GRIP_ANGLE = 135

/** Degrees clockwise from "up" of the direction from `centre` to `point` (0..360). */
export function angleFromCentre(centre: XY, point: XY): number {
  const deg = (Math.atan2(point.x - centre.x, centre.y - point.y) * 180) / Math.PI
  return normaliseRotation(deg)
}

/** Where a point `distance` away from `centre` in direction `angle` lies. */
export function pointAtAngle(centre: XY, angle: number, distance: number): XY {
  const rad = (angle * Math.PI) / 180
  return { x: centre.x + Math.sin(rad) * distance, y: centre.y - Math.cos(rad) * distance }
}

/** `deg` rounded to the nearest multiple of `step` (0..360). */
export function snapAngle(deg: number, step: number = ROTATION_STEP): number {
  if (!(step > 0)) return normaliseRotation(deg)
  return normaliseRotation(Math.round(deg / step) * step)
}

/**
 * The turn of a decoration while its rotate grip is dragged: it turns by as
 * much as the pointer went round the centre since the press, so grabbing the
 * grip slightly off-centre does not make the glyph jump. `snap` (Shift) rounds
 * the result to `ROTATION_STEP`.
 */
export function rotationFromDrag(
  startRotation: number,
  startAngle: number,
  currentAngle: number,
  snap = false,
): number {
  const raw = startRotation + (currentAngle - startAngle)
  return snap ? snapAngle(raw) : normaliseRotation(raw)
}

/** Below this distance (plan units) from the centre a resize drag holds still. */
const MIN_DISTANCE = 1e-6

/**
 * The size of a decoration while its corner grip is dragged: the size at the
 * press, times how much farther from (or nearer to) the centre the pointer is
 * now. Clamped to `PROP_SCALE_RANGE`, rounded like every stored size.
 */
export function scaleFromDrag(startScale: number, startDistance: number, distance: number): number {
  if (!(startDistance > MIN_DISTANCE) || !Number.isFinite(distance)) {
    return roundScale(clampPropScale(startScale))
  }
  return roundScale(clampPropScale((startScale * Math.max(0, distance)) / startDistance))
}

export function roundScale(scale: number): number {
  return Math.round(scale * 1000) / 1000
}

/** The distance between two points. */
export function distance(a: XY, b: XY): number {
  return Math.hypot(b.x - a.x, b.y - a.y)
}

const RESIZE_CURSORS = ['ns-resize', 'nesw-resize', 'ew-resize', 'nwse-resize'] as const

/** The resize cursor that best matches a grip in direction `angle` from the centre. */
export function resizeCursor(angle: number): (typeof RESIZE_CURSORS)[number] {
  const octant = Math.round(normaliseRotation(angle) / 45) % 4
  return RESIZE_CURSORS[octant]!
}

/** Gap (CSS px) between a decoration's glyph and its selection ring. */
export const RING_GAP_PX = 4

/** Radius of the selection ring round a glyph of `glyphRadius` plan units. */
export function propRingRadius(glyphRadius: number, unitsPerPixel: number): number {
  return glyphRadius + RING_GAP_PX * unitsPerPixel
}

/**
 * The distance from the centre a resize drag measures against: the press's own
 * distance, but never less than `floor` — the glyph's radius, the nearest a
 * press on the resize grip can land (its hit circle stays off the glyph). A
 * press near the centre would otherwise make the smallest movement blow the
 * size up to its limit, while a floor any further out would make the glyph
 * jump on the first move.
 */
export function scaleStartDistance(pressDistance: number, floor: number): number {
  return Math.max(pressDistance, floor)
}

export type PropGrips = {
  /** Radius of the selection ring. */
  ring: number
  /** Where the rotate grip's stalk leaves the ring, and the grip itself. */
  stalk: XY
  rotate: XY
  resize: XY
  /**
   * Centre of the resize grip's invisible hit circle: pushed outwards along
   * the grip's direction until a circle of `hitRadius` no longer reaches into
   * the glyph, so a press on the glyph moves it rather than resizing it. The
   * visible grip stays on the ring, inside that circle.
   */
  resizeHit: XY
  resizeAngle: number
}

/**
 * Where the grips of a decoration go: the rotate grip `stalkUnits` beyond the
 * ring in the direction the glyph's top points, the resize grip on the ring at
 * `RESIZE_GRIP_ANGLE` further round. Both turn with the glyph, so they never
 * meet.
 */
export function propGrips(
  centre: XY,
  rotation: number,
  ringRadius: number,
  stalkUnits: number,
  glyphRadius = ringRadius,
  hitRadius = 0,
): PropGrips {
  const resizeAngle = normaliseRotation(rotation + RESIZE_GRIP_ANGLE)
  return {
    ring: ringRadius,
    stalk: pointAtAngle(centre, rotation, ringRadius),
    rotate: pointAtAngle(centre, rotation, ringRadius + stalkUnits),
    resize: pointAtAngle(centre, resizeAngle, ringRadius),
    resizeHit: pointAtAngle(centre, resizeAngle, Math.max(ringRadius, glyphRadius + hitRadius)),
    resizeAngle,
  }
}
