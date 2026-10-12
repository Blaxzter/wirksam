import { type MaybeRefOrGetter, type Ref, computed, ref, toValue, watch } from 'vue'

import { useElementSize, useEventListener } from '@vueuse/core'

import {
  type Point,
  type ViewBox,
  clientToImage,
  fitViewBox,
  panBy,
  unitsPerPixel as unitsPerPixelFor,
  viewBoxToString,
  zoomAt,
} from '@/lib/venue-map'

export interface PanZoomOptions {
  /** Image width in image units (the plan's `image_width`). */
  width: MaybeRefOrGetter<number>
  /** Image height in image units (the plan's `image_height`). */
  height: MaybeRefOrGetter<number>
  /** How far in the user may zoom, as a multiple of the fitted view. Default 8. */
  maxZoom?: number
  /** `false` switches all gesture handling off (a static mini-map). Default `true`. */
  enabled?: MaybeRefOrGetter<boolean>
}

/** Movement (CSS px) after which a press counts as a drag, not a tap. */
const DRAG_THRESHOLD = 4
/** Two taps closer than this (ms and px) are a double tap. */
const DOUBLE_TAP_MS = 300
const DOUBLE_TAP_PX = 30
/** Zoom step for the +/− buttons and for a double click or double tap. */
const BUTTON_STEP = 1.5
const DOUBLE_STEP = 2
/** Wheel sensitivity: `exp(-deltaY · k)` keeps trackpads and wheels comparable. */
const WHEEL_K = 0.002
const LINE_HEIGHT_PX = 16

const distance = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y)
const midpoint = (a: Point, b: Point): Point => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 })

/**
 * Pan, pinch and wheel zoom for an SVG whose user space is image units.
 *
 * Bind `viewBoxAttr` to the SVG's `viewBox` and give it `touch-action: none`
 * (Tailwind `touch-none`), otherwise the browser scrolls the page instead of
 * delivering pointer events.
 *
 * - one pointer pans, two pointers pinch around their midpoint;
 * - the wheel zooms around the cursor;
 * - a double click (mouse) or double tap (touch, pen) zooms in ×2 there.
 *
 * Marker click handlers should bail out while `isGesturing` is true: it turns
 * on once a press has moved more than 4 px (or a second finger lands) and
 * stays on until the next press, so the `click` that follows a drag is
 * recognisable. Pointer capture is only taken once a press becomes a drag —
 * capturing on `pointerdown` would retarget that `click` to the SVG itself.
 */
export function usePanZoom(svgRef: Ref<SVGSVGElement | null | undefined>, options: PanZoomOptions) {
  const maxZoom = options.maxZoom ?? 8
  const W = () => toValue(options.width)
  const H = () => toValue(options.height)
  const enabled = () => toValue(options.enabled ?? true)

  const viewBox = ref<ViewBox>(fitViewBox(W(), H()))
  const viewBoxAttr = computed(() => viewBoxToString(viewBox.value))
  const isGesturing = ref(false)

  const { width: clientWidth, height: clientHeight } = useElementSize(svgRef)
  /** Image units per CSS pixel — scale markers by this for a constant screen size. */
  const unitsPerPixel = computed(() =>
    unitsPerPixelFor(viewBox.value, clientWidth.value, clientHeight.value),
  )

  const minW = () => W() / maxZoom
  const maxW = () => W()

  function rect() {
    const el = svgRef.value
    return el ? el.getBoundingClientRect() : { left: 0, top: 0, width: 0, height: 0 }
  }

  /** A client (screen) point → image units, under the current view box. */
  function clientToSvg(clientX: number, clientY: number): Point {
    return clientToImage(viewBox.value, rect(), clientX, clientY)
  }

  function zoomAround(factor: number, point: Point) {
    viewBox.value = zoomAt(viewBox.value, factor, point.x, point.y, W(), H(), minW(), maxW())
  }

  function zoomAroundCentre(factor: number) {
    const vb = viewBox.value
    zoomAround(factor, { x: vb.x + vb.w / 2, y: vb.y + vb.h / 2 })
  }

  function reset() {
    viewBox.value = fitViewBox(W(), H())
  }

  /** Centre the normalised point `(x01, y01)` at `zoom`× the fitted view. */
  function focus(x01: number, y01: number, zoom = 3) {
    const w = Math.min(maxW(), Math.max(minW(), W() / zoom))
    const h = W() > 0 ? (w * H()) / W() : 0
    viewBox.value = panBy({ x: x01 * W() - w / 2, y: y01 * H() - h / 2, w, h }, 0, 0, W(), H())
  }

  const zoomIn = () => zoomAroundCentre(BUTTON_STEP)
  const zoomOut = () => zoomAroundCentre(1 / BUTTON_STEP)

  // A new plan (or a replaced image of another size) starts fitted.
  watch([W, H], reset)

  // ── Pointer handling ───────────────────────────────────────────────────
  const pointers = new Map<number, Point>()
  let pressStart: Point | null = null
  let lastTap: { time: number; point: Point } | null = null

  function capture(pointerId: number) {
    try {
      svgRef.value?.setPointerCapture?.(pointerId)
    } catch {
      // The pointer may already be gone (released between events); harmless.
    }
  }

  function onPointerDown(e: PointerEvent) {
    if (!enabled()) return
    if (e.pointerType === 'mouse' && e.button !== 0) return
    const point = { x: e.clientX, y: e.clientY }
    pointers.set(e.pointerId, point)
    if (pointers.size === 1) {
      pressStart = point
      isGesturing.value = false
    } else {
      // A second finger is always a gesture, never a tap.
      isGesturing.value = true
      for (const id of pointers.keys()) capture(id)
    }
  }

  function onPointerMove(e: PointerEvent) {
    const prev = pointers.get(e.pointerId)
    if (!prev) return
    const cur = { x: e.clientX, y: e.clientY }

    if (pointers.size === 1) {
      if (!isGesturing.value) {
        if (!pressStart || distance(cur, pressStart) <= DRAG_THRESHOLD) return
        isGesturing.value = true
        capture(e.pointerId)
      }
      const k = unitsPerPixelFor(viewBox.value, rect().width, rect().height)
      viewBox.value = panBy(viewBox.value, -(cur.x - prev.x) * k, -(cur.y - prev.y) * k, W(), H())
      pointers.set(e.pointerId, cur)
      return
    }

    if (pointers.size === 2) {
      const other = [...pointers.entries()].find(([id]) => id !== e.pointerId)![1]
      const before = distance(prev, other)
      const after = distance(cur, other)
      const oldMid = midpoint(prev, other)
      const newMid = midpoint(cur, other)
      if (before > 0 && after > 0) zoomAround(after / before, clientToSvg(oldMid.x, oldMid.y))
      // Then follow the midpoint, so two fingers moving together also pan.
      const k = unitsPerPixelFor(viewBox.value, rect().width, rect().height)
      viewBox.value = panBy(
        viewBox.value,
        -(newMid.x - oldMid.x) * k,
        -(newMid.y - oldMid.y) * k,
        W(),
        H(),
      )
    }
    pointers.set(e.pointerId, cur)
  }

  function onPointerEnd(e: PointerEvent) {
    if (!pointers.has(e.pointerId)) return
    const wasTap = pointers.size === 1 && !isGesturing.value
    pointers.delete(e.pointerId)
    if (pointers.size === 0) pressStart = null

    if (!wasTap || e.type !== 'pointerup' || e.pointerType === 'mouse') return
    // Double tap — touch and pen only; a mouse gets the native `dblclick`.
    const point = { x: e.clientX, y: e.clientY }
    const now = Date.now()
    if (
      lastTap &&
      now - lastTap.time <= DOUBLE_TAP_MS &&
      distance(point, lastTap.point) <= DOUBLE_TAP_PX
    ) {
      lastTap = null
      zoomAround(DOUBLE_STEP, clientToSvg(point.x, point.y))
    } else {
      lastTap = { time: now, point }
    }
  }

  function onWheel(e: WheelEvent) {
    if (!enabled()) return
    e.preventDefault()
    const delta = e.deltaMode === 1 ? e.deltaY * LINE_HEIGHT_PX : e.deltaY
    zoomAround(Math.exp(-delta * WHEEL_K), clientToSvg(e.clientX, e.clientY))
  }

  function onDoubleClick(e: MouseEvent) {
    if (!enabled()) return
    zoomAround(DOUBLE_STEP, clientToSvg(e.clientX, e.clientY))
  }

  useEventListener(svgRef, 'pointerdown', onPointerDown)
  useEventListener(svgRef, 'pointermove', onPointerMove)
  useEventListener(svgRef, 'pointerup', onPointerEnd)
  useEventListener(svgRef, 'pointercancel', onPointerEnd)
  useEventListener(svgRef, 'wheel', onWheel, { passive: false })
  useEventListener(svgRef, 'dblclick', onDoubleClick)

  return {
    viewBox,
    viewBoxAttr,
    unitsPerPixel,
    isGesturing,
    clientToSvg,
    reset,
    focus,
    zoomIn,
    zoomOut,
  }
}

export type PanZoom = ReturnType<typeof usePanZoom>
