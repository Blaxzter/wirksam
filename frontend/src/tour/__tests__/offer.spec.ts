// @vitest-environment jsdom
/**
 * The contract module both ends of the tour talk through.
 *
 * Two of its three functions are one line of state each; the third is the one
 * worth a spec, because the thing that is easy to get wrong about it is
 * invisible on screen — `requestTour` must clear the offer *without* releasing
 * the quiet flag, or the join-request toast held back for the welcome dialog is
 * flushed onto the tour's own first step, which is the exact collision
 * `tour/quiet.ts` exists to prevent.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  TOUR_RESTART_EVENT,
  TOUR_STOP_EVENT,
  declineTour,
  endTour,
  offerTour,
  offeredTrack,
  requestTour,
} from '@/tour/offer'
import { isTourRunning, setTourRunning, whenTourIsOver } from '@/tour/quiet'

beforeEach(() => {
  // Both modules are singletons with module-level state, so a case that ends
  // mid-offer would hand the next one a question already on screen.
  declineTour()
  setTourRunning(false)
})

afterEach(() => {
  declineTour()
  setTourRunning(false)
})

describe('tour offer', () => {
  it('puts a track on offer and holds the screen while the question is up', () => {
    const held = vi.fn()

    offerTour('manager')

    expect(offeredTrack.value).toBe('manager')
    expect(isTourRunning()).toBe(true)
    whenTourIsOver(held)
    expect(held).not.toHaveBeenCalled()
  })

  it('releases the held work when the visitor would rather look around', () => {
    const held = vi.fn()
    offerTour('helper')
    whenTourIsOver(held)

    declineTour()

    expect(offeredTrack.value).toBeNull()
    expect(isTourRunning()).toBe(false)
    expect(held).toHaveBeenCalledOnce()
  })

  it('asks the engine for the track, and keeps holding while it starts', () => {
    const held = vi.fn()
    const listener = vi.fn()
    window.addEventListener(TOUR_RESTART_EVENT, listener)
    offerTour('manager')
    whenTourIsOver(held)

    requestTour('manager')

    // The dialog is gone, but the tour it asked for has not drawn its first
    // step yet — anything released here would land on top of it.
    expect(offeredTrack.value).toBeNull()
    expect(isTourRunning()).toBe(true)
    expect(held).not.toHaveBeenCalled()

    expect(listener).toHaveBeenCalledOnce()
    const event = listener.mock.calls[0][0] as CustomEvent<{ track?: string }>
    expect(event.detail.track).toBe('manager')
    window.removeEventListener(TOUR_RESTART_EVENT, listener)
  })

  it('wipes the slate for a second demo in the same tab', () => {
    const held = vi.fn()
    const listener = vi.fn()
    window.addEventListener(TOUR_STOP_EVENT, listener)
    offerTour('helper')
    whenTourIsOver(held)

    endTour()

    expect(offeredTrack.value).toBeNull()
    expect(listener).toHaveBeenCalledOnce()
    // Nothing is holding the screen now — neither a question nor a popover.
    expect(isTourRunning()).toBe(false)
    expect(held).toHaveBeenCalledOnce()
    window.removeEventListener(TOUR_STOP_EVENT, listener)
  })

  it('can be asked for a tour that was never offered', () => {
    // The demo banner's "restart the tour", which never goes through an offer.
    const listener = vi.fn()
    window.addEventListener(TOUR_RESTART_EVENT, listener)

    requestTour('helper')

    expect(offeredTrack.value).toBeNull()
    expect(listener).toHaveBeenCalledOnce()
    window.removeEventListener(TOUR_RESTART_EVENT, listener)
  })
})
