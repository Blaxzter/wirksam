/**
 * Asking for a tour, and being asked whether you want one.
 *
 * Two facts that the chrome and the engine both need and neither should own:
 *
 *  1. **A tour has been offered.** `tour/install.ts` decides that a demo
 *     session has just landed on its dashboard; `SandboxWelcomeDialog.vue` is
 *     what the visitor actually sees, and it lives in `App.vue`, nowhere near
 *     the router hook that made the decision. A module-level `ref` is the
 *     shortest honest line between the two.
 *  2. **A tour has been asked for.** The demo banner's "show me around" and the
 *     welcome dialog's "yes please" both mean the same thing, and both are
 *     components that must not import `tour/engine.ts` — and with it driver.js
 *     — merely to say so. They dispatch a window event the engine listens for.
 *
 * Which is why this module imports nothing but `vue`, `tour/quiet.ts` and a
 * type: everything that can ask for a tour can afford to import *this*.
 *
 * ── Why offering also goes quiet ─────────────────────────────────────────────
 * `setTourRunning` is what keeps `notifyPendingJoinRequests` off a popover it
 * would cover, and the welcome dialog has exactly the same problem — it is
 * modal, so a toast landing behind it is a toast with dead buttons. Holding
 * from the moment the offer is made means the question gets a clean screen
 * either way: accept and the engine keeps holding, decline and the held work
 * runs the moment the visitor is free to click it.
 */
import { readonly, ref } from 'vue'

import { setTourRunning } from '@/tour/quiet'
import type { TourTrackId } from '@/tour/types'

/**
 * Dispatched on `window` as
 * `new CustomEvent(TOUR_RESTART_EVENT, { detail: { track: 'helper' } })`.
 *
 * `tour/install.ts` is the only listener, and it starts the named track from
 * the beginning. There is deliberately no response: if nothing is listening —
 * a page that never installed the tour — nothing happens.
 */
export const TOUR_RESTART_EVENT = 'wirksam:restart-tour'

/**
 * Dispatched on `window` to take a running tour off the screen.
 *
 * The counterpart to the one above, and needed for the same reason: the thing
 * that knows a tour has become irrelevant — `stores/sandbox.ts`, minting a
 * second demo in a tab that still has the first one's tour open — is not
 * allowed to import the engine either.
 */
export const TOUR_STOP_EVENT = 'wirksam:stop-tour'

const offered = ref<TourTrackId | null>(null)

/** The track the visitor has been offered and not yet answered, or `null`. */
export const offeredTrack = readonly(offered)

/** Put the question on screen. */
export function offerTour(track: TourTrackId): void {
  offered.value = track
  setTourRunning(true)
}

/** "No thanks, I'll look around myself." */
export function declineTour(): void {
  offered.value = null
  setTourRunning(false)
}

/**
 * Run a track from the top, whoever asked.
 *
 * The offer is cleared without releasing the quiet flag: the engine's own
 * `start()` sets it again a moment later, and letting it drop in between would
 * flush a held toast onto the tour's first step — the exact collision the flag
 * exists to prevent.
 */
export function requestTour(track: TourTrackId): void {
  offered.value = null
  window.dispatchEvent(new CustomEvent(TOUR_RESTART_EVENT, { detail: { track } }))
}

/**
 * Put away whatever the tour currently has on screen — an unanswered offer, a
 * running track, or nothing at all.
 *
 * For the one caller that has to wipe the slate rather than answer anything: a
 * new demo in the same tab, which is a new first impression and must not
 * inherit the last one's half-finished tour. Releases the quiet flag, because
 * nothing is holding the screen afterwards.
 */
export function endTour(): void {
  offered.value = null
  window.dispatchEvent(new CustomEvent(TOUR_STOP_EVENT))
  setTourRunning(false)
}
