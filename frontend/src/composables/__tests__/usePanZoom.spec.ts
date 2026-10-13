// @vitest-environment jsdom
import { effectScope, nextTick, ref } from 'vue'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { usePanZoom } from '@/composables/usePanZoom'

/**
 * A 1000×500 plan shown in a 500×250 element: two image units per pixel, no
 * letterboxing. That makes every expected number below easy to derive.
 */
const W = 1000
const H = 500

let svg: SVGSVGElement
let scope: ReturnType<typeof effectScope>

function mount(
  opts: {
    width?: number
    height?: number
    enabled?: boolean
    maxZoom?: number
    panFilter?: (e: PointerEvent) => boolean
    dblclickZoom?: boolean
  } = {},
) {
  svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  svg.getBoundingClientRect = () =>
    ({ left: 0, top: 0, width: 500, height: 250, right: 500, bottom: 250 }) as DOMRect
  document.body.appendChild(svg)
  const svgRef = ref<SVGSVGElement | null>(svg)
  const width = ref(opts.width ?? W)
  const height = ref(opts.height ?? H)
  const enabled = ref(opts.enabled ?? true)
  scope = effectScope()
  const pz = scope.run(() =>
    usePanZoom(svgRef, {
      width,
      height,
      enabled,
      maxZoom: opts.maxZoom,
      panFilter: opts.panFilter,
      dblclickZoom: opts.dblclickZoom,
    }),
  )!
  return { pz, width, height, enabled }
}

function pointer(
  type: string,
  init: { id?: number; x: number; y: number; pointerType?: string; button?: number },
) {
  const event = new PointerEvent(type, {
    bubbles: true,
    cancelable: true,
    clientX: init.x,
    clientY: init.y,
    pointerId: init.id ?? 1,
    pointerType: init.pointerType ?? 'touch',
    button: init.button ?? 0,
  })
  svg.dispatchEvent(event)
  return event
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-12T10:00:00Z'))
})

afterEach(() => {
  scope.stop()
  svg.remove()
  vi.useRealTimers()
})

describe('usePanZoom', () => {
  it('starts fitted and serialises the view box', () => {
    const { pz } = mount()
    expect(pz.viewBox.value).toEqual({ x: 0, y: 0, w: W, h: H })
    expect(pz.viewBoxAttr.value).toBe('0 0 1000 500')
    // No layout in jsdom (no ResizeObserver) → the 1:1 fallback.
    expect(pz.unitsPerPixel.value).toBe(1)
  })

  it('pans with one pointer once the drag threshold is passed', () => {
    const { pz } = mount()
    pointer('pointerdown', { x: 100, y: 100 })
    pointer('pointermove', { x: 102, y: 101 })
    // Within 4 px: still a tap, nothing moves.
    expect(pz.viewBox.value.x).toBe(0)
    expect(pz.isGesturing.value).toBe(false)

    pointer('pointermove', { x: 90, y: 95 })
    expect(pz.isGesturing.value).toBe(true)
    // Moved −10/−5 px from the press at 2 units per pixel.
    expect(pz.viewBox.value).toMatchObject({ x: 20, y: 10 })

    pointer('pointermove', { x: 80, y: 95 })
    expect(pz.viewBox.value).toMatchObject({ x: 40, y: 10 })
    pointer('pointerup', { x: 80, y: 95 })
    // Stays set so the click that follows the drag can be ignored…
    expect(pz.isGesturing.value).toBe(true)
    // …until the next press.
    pointer('pointerdown', { x: 0, y: 0 })
    expect(pz.isGesturing.value).toBe(false)
  })

  it('clamps panning so part of the image stays visible', () => {
    const { pz } = mount()
    pointer('pointerdown', { x: 0, y: 0 })
    pointer('pointermove', { x: -5000, y: -5000 })
    expect(pz.viewBox.value).toMatchObject({ x: 900, y: 450 })
  })

  it('ignores moves of a pointer that never went down', () => {
    const { pz } = mount()
    pointer('pointermove', { x: 300, y: 300 })
    expect(pz.viewBox.value.x).toBe(0)
  })

  it('ignores the right mouse button', () => {
    const { pz } = mount()
    pointer('pointerdown', { x: 100, y: 100, pointerType: 'mouse', button: 2 })
    pointer('pointermove', { x: 0, y: 0, pointerType: 'mouse' })
    expect(pz.viewBox.value.x).toBe(0)
  })

  it('pinches with two pointers around their midpoint', () => {
    const { pz } = mount()
    pointer('pointerdown', { id: 1, x: 200, y: 125 })
    pointer('pointerdown', { id: 2, x: 300, y: 125 })
    expect(pz.isGesturing.value).toBe(true)

    // Spread from 100 px to 200 px apart → zoom ×2 around the midpoint (250,125)
    // → image point (500,250); the midpoint then moves 50 px right → pan.
    pointer('pointermove', { id: 2, x: 400, y: 125 })
    const vb = pz.viewBox.value
    expect(vb.w).toBeCloseTo(500)
    expect(vb.h).toBeCloseTo(250)
    // Zoom alone would give x=250; the midpoint moved +50 px at 1 unit/px.
    expect(vb.x).toBeCloseTo(200)

    // Lifting one finger hands over to a pan with the other.
    pointer('pointerup', { id: 2, x: 400, y: 125 })
    pointer('pointermove', { id: 1, x: 190, y: 125 })
    expect(pz.viewBox.value.x).toBeCloseTo(210)
    pointer('pointercancel', { id: 1, x: 190, y: 125 })
  })

  it('zooms with the wheel around the cursor', () => {
    const { pz } = mount()
    const event = new WheelEvent('wheel', {
      deltaY: -100,
      clientX: 250,
      clientY: 125,
      cancelable: true,
    })
    svg.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    const factor = Math.exp(0.2)
    expect(pz.viewBox.value.w).toBeCloseTo(W / factor)
    // The cursor sits on the image centre, so the centre stays put.
    expect(pz.viewBox.value.x + pz.viewBox.value.w / 2).toBeCloseTo(500)
  })

  it('reads line-based wheel deltas as 16 px lines', () => {
    const { pz } = mount()
    svg.dispatchEvent(
      new WheelEvent('wheel', { deltaY: -5, deltaMode: 1, clientX: 250, clientY: 125 }),
    )
    expect(pz.viewBox.value.w).toBeCloseTo(W / Math.exp(5 * 16 * 0.002))
  })

  it('zooms ×2 on a mouse double click', () => {
    const { pz } = mount()
    svg.dispatchEvent(new MouseEvent('dblclick', { clientX: 0, clientY: 0 }))
    expect(pz.viewBox.value).toEqual({ x: 0, y: 0, w: 500, h: 250 })
  })

  it('zooms ×2 on a double tap, but not on two slow taps', () => {
    const { pz } = mount()
    pointer('pointerdown', { x: 250, y: 125 })
    pointer('pointerup', { x: 250, y: 125 })
    vi.setSystemTime(Date.now() + 500)
    pointer('pointerdown', { x: 250, y: 125 })
    pointer('pointerup', { x: 250, y: 125 })
    expect(pz.viewBox.value.w).toBe(W)

    vi.setSystemTime(Date.now() + 100)
    pointer('pointerdown', { x: 250, y: 125 })
    pointer('pointerup', { x: 250, y: 125 })
    expect(pz.viewBox.value.w).toBe(500)
  })

  it('does not treat mouse clicks or drags as taps', () => {
    const { pz } = mount()
    for (let i = 0; i < 2; i++) {
      pointer('pointerdown', { x: 250, y: 125, pointerType: 'mouse' })
      pointer('pointerup', { x: 250, y: 125, pointerType: 'mouse' })
    }
    expect(pz.viewBox.value.w).toBe(W)
    // A drag ending in pointerup is not a tap either.
    pointer('pointerdown', { x: 250, y: 125 })
    pointer('pointermove', { x: 270, y: 125 })
    pointer('pointerup', { x: 270, y: 125 })
    pointer('pointerup', { x: 270, y: 125 })
    expect(pz.viewBox.value.w).toBe(W)
  })

  it('zoomIn / zoomOut step around the centre and respect the limits', () => {
    const { pz } = mount({ maxZoom: 2 })
    pz.zoomIn()
    expect(pz.viewBox.value.w).toBeCloseTo(W / 1.5)
    pz.zoomIn()
    pz.zoomIn()
    expect(pz.viewBox.value.w).toBeCloseTo(W / 2)
    pz.zoomOut()
    pz.zoomOut()
    pz.zoomOut()
    expect(pz.viewBox.value).toEqual({ x: 0, y: 0, w: W, h: H })
  })

  it('focus centres a normalised point at the given zoom, then reset fits again', () => {
    const { pz } = mount()
    pz.focus(0.5, 0.5)
    const vb = pz.viewBox.value
    expect(vb.w).toBeCloseTo(W / 3)
    expect(vb.x + vb.w / 2).toBeCloseTo(500)
    expect(vb.y + vb.h / 2).toBeCloseTo(250)

    pz.focus(0.25, 0.25, 100)
    expect(pz.viewBox.value.w).toBeCloseTo(W / 8)

    pz.reset()
    expect(pz.viewBox.value).toEqual({ x: 0, y: 0, w: W, h: H })
  })

  it('focus on an empty image does not divide by zero', () => {
    const { pz } = mount({ width: 0, height: 0 })
    pz.focus(0.5, 0.5)
    expect(pz.viewBox.value.h).toBe(0)
  })

  it('refits when the image size changes', async () => {
    const { pz, width, height } = mount()
    pz.zoomIn()
    width.value = 800
    height.value = 600
    await nextTick()
    expect(pz.viewBox.value).toEqual({ x: 0, y: 0, w: 800, h: 600 })
  })

  it('converts client points to image units', () => {
    const { pz } = mount()
    expect(pz.clientToSvg(250, 125)).toEqual({ x: 500, y: 250 })
  })

  it('does nothing while disabled', () => {
    const { pz } = mount({ enabled: false })
    pointer('pointerdown', { x: 100, y: 100 })
    pointer('pointermove', { x: 0, y: 0 })
    const wheel = new WheelEvent('wheel', { deltaY: -100, cancelable: true })
    svg.dispatchEvent(wheel)
    svg.dispatchEvent(new MouseEvent('dblclick'))
    expect(pz.viewBox.value).toEqual({ x: 0, y: 0, w: W, h: H })
    // The page may still scroll past a static map.
    expect(wheel.defaultPrevented).toBe(false)
  })

  it('survives pointer capture failing', () => {
    const { pz } = mount()
    svg.setPointerCapture = () => {
      throw new Error('InvalidPointerId')
    }
    pointer('pointerdown', { x: 100, y: 100 })
    pointer('pointermove', { x: 50, y: 100 })
    expect(pz.viewBox.value.x).toBe(100)
  })

  it('works without an element', () => {
    const svgRef = ref<SVGSVGElement | null>(null)
    svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
    scope = effectScope()
    const pz = scope.run(() => usePanZoom(svgRef, { width: W, height: H }))!
    expect(pz.clientToSvg(10, 20)).toEqual({ x: 10, y: 20 })
  })

  it('counts the pointers that are down', () => {
    const { pz } = mount()
    expect(pz.pointerCount.value).toBe(0)
    pointer('pointerdown', { id: 1, x: 10, y: 10 })
    pointer('pointerdown', { id: 2, x: 20, y: 10 })
    expect(pz.pointerCount.value).toBe(2)
    pointer('pointerup', { id: 1, x: 10, y: 10 })
    pointer('pointercancel', { id: 2, x: 20, y: 10 })
    expect(pz.pointerCount.value).toBe(0)
  })

  it('does not pan with a press the filter rejects, but pinches once a second finger lands', () => {
    // A drawing tool: single touches draw, they do not pan.
    const { pz } = mount({ panFilter: () => false })
    pointer('pointerdown', { id: 1, x: 200, y: 125 })
    pointer('pointermove', { id: 1, x: 100, y: 125 })
    expect(pz.viewBox.value.x).toBe(0)
    expect(pz.isGesturing.value).toBe(false)
    expect(pz.pointerCount.value).toBe(1)

    pointer('pointermove', { id: 1, x: 200, y: 125 })
    pointer('pointerdown', { id: 2, x: 300, y: 125 })
    expect(pz.isGesturing.value).toBe(true)
    pointer('pointermove', { id: 2, x: 400, y: 125 })
    expect(pz.viewBox.value.w).toBeCloseTo(500)
    // After the pinch the remaining finger pans like any other.
    pointer('pointerup', { id: 2, x: 400, y: 125 })
    const x = pz.viewBox.value.x
    pointer('pointermove', { id: 1, x: 190, y: 125 })
    expect(pz.viewBox.value.x).toBeCloseTo(x + 10)
    pointer('pointerup', { id: 1, x: 190, y: 125 })
  })

  it('ignores a rejected mouse press entirely, and pans with an accepted middle button', () => {
    const { pz } = mount({ panFilter: (e) => e.button === 1 })
    pointer('pointerdown', { x: 100, y: 100, pointerType: 'mouse', button: 0 })
    expect(pz.pointerCount.value).toBe(0)
    pointer('pointermove', { x: 0, y: 100, pointerType: 'mouse' })
    expect(pz.viewBox.value.x).toBe(0)
    pointer('pointerdown', { x: 100, y: 100, pointerType: 'mouse', button: 1 })
    pointer('pointermove', { x: 50, y: 100, pointerType: 'mouse' })
    expect(pz.viewBox.value.x).toBe(100)
  })

  it('a rejected tap is not half of a double tap', () => {
    const { pz } = mount({ panFilter: () => false })
    for (let i = 0; i < 2; i++) {
      pointer('pointerdown', { x: 250, y: 125 })
      pointer('pointerup', { x: 250, y: 125 })
    }
    expect(pz.viewBox.value.w).toBe(W)
  })

  it('can switch double-click and double-tap zoom off', () => {
    const { pz } = mount({ dblclickZoom: false })
    svg.dispatchEvent(new MouseEvent('dblclick', { clientX: 0, clientY: 0 }))
    for (let i = 0; i < 2; i++) {
      pointer('pointerdown', { x: 250, y: 125 })
      pointer('pointerup', { x: 250, y: 125 })
    }
    expect(pz.viewBox.value.w).toBe(W)
  })
})
