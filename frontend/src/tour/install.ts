/**
 * Wiring the guided tour into the running app.
 *
 * Three jobs, all of them about *when* a tour starts and restarts:
 *
 *  1. `router.afterEach` hands every settled navigation to the engine, which is
 *     what makes a step survive a route change, a view remount and a full page
 *     reload — the step index itself is in `sessionStorage`, so a reload
 *     arrives here with the tour already restored and only needs re-drawing.
 *  2. A `wirksam:restart-tour` window event — dispatched by the demo banner and
 *     by the welcome dialog — starts a named track from the beginning.
 *  3. First arrival at the dashboard in a demo session *offers* the matching
 *     track, exactly once per sitting, and leaves the answer to the visitor.
 *
 * Installed from `main.ts` after Pinia, the router and i18n, and before mount.
 * Nothing here touches a store at install time: `stores/auth.ts` calls
 * `useI18n()` in its setup, which throws outside a component, so it may only be
 * reached from a handler that runs after `App.vue` has already created it.
 */
import type { RouteLocationNormalized, Router } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { useTourStore } from '@/stores/tour'

import { useChangelogStatus } from '@/composables/useChangelogStatus'

import { hasAutoStarted, markAutoStarted } from '@/tour/autostart'
import { type TourController, createTourController } from '@/tour/engine'
import { TOUR_RESTART_EVENT, TOUR_STOP_EVENT, offerTour, offeredTrack } from '@/tour/offer'
import { setTourRunning } from '@/tour/quiet'
import type { TourTrackId } from '@/tour/types'

/**
 * Re-exported because this module was the constant's home for two releases and
 * because it reads better at the listener below. `tour/offer.ts` owns it now,
 * so that a component can dispatch the event without importing the engine.
 */
export { TOUR_RESTART_EVENT }

/** The screen a demo session lands on, and the only place a tour offers itself. */
const DASHBOARD_ROUTE = 'home'

/**
 * Keep the "What's New" dialog off a running tour.
 *
 * `PostAuthLayout` opens it from `onMounted` the first time a browser sees a
 * new release, and a modal that takes focus and dims the page is the one thing
 * that can break a tour outright. The lever is the same one
 * `testing/fake-session.ts` pulls for the same reason — the
 * `wirksam-last-seen-changelog` key — reached through `markAsSeen()` so that it
 * writes the *real* latest version rather than an unreachable one: a visitor
 * who signs up after the demo still gets the dialog for the next release.
 */
function suppressWhatsNew(): void {
  useChangelogStatus().markAsSeen()
}

function beginTour(controller: TourController, track: TourTrackId): void {
  suppressWhatsNew()
  controller.start(track)
}

/**
 * Offer the track that matches who the demo signed the visitor in as, once.
 *
 * An *offer* rather than a start: a tour that begins on its own is a tour
 * nobody agreed to, and the first thing it did was dim the screen the visitor
 * had come to look at. `SandboxWelcomeDialog.vue` says hello, explains that the
 * event is theirs to break, and asks — and only a yes reaches `beginTour`, by
 * way of the same window event the banner uses.
 *
 * The role is read off the profile rather than remembered from the request that
 * created the session, so it survives a reload: a demo `manager` owns their
 * seeded event, a demo `helper` is only a member of it.
 */
function maybeOfferTour(to: RouteLocationNormalized): boolean {
  if (to.name !== DASHBOARD_ROUTE) return false
  if (hasAutoStarted()) return false
  // A tour restored from `sessionStorage` is mid-flight; asking whether they
  // would like one would be asking a question they answered before the reload.
  if (useTourStore().status === 'running') return false

  const auth = useAuthStore()
  if (!auth.profile?.is_sandbox) return false

  markAutoStarted()
  // Suppressed for the greeting, not only for the tour: `PostAuthLayout` opens
  // "What's New" from `onMounted`, and a second modal stacking on the question
  // is exactly the collision this call exists to prevent. Nothing is lost — a
  // demo account is minutes old, so it has no releases to have missed.
  suppressWhatsNew()
  offerTour(auth.canManageEvent(auth.selectedEventId) ? 'manager' : 'helper')
  return true
}

export function installTour(router: Router): void {
  const controller = createTourController(router)

  window.addEventListener(TOUR_RESTART_EVENT, (event) => {
    const detail = (event as CustomEvent<{ track?: TourTrackId }>).detail
    // Anything that is not the manager track is the helper track: the volunteer
    // path is the one that makes sense to somebody who cannot manage anything.
    beginTour(controller, detail?.track === 'manager' ? 'manager' : 'helper')
  })

  // A second demo in the same tab. Nothing else ends a tour from outside it,
  // and this one has to, because the tour that is on screen belongs to a
  // session that no longer exists — `stop()` rather than `finish()`, since
  // nobody reached the end of anything.
  window.addEventListener(TOUR_STOP_EVENT, () => controller.stop())

  router.afterEach((to) => {
    // A tour restored from `sessionStorage` by a reload is already running and
    // nothing called `start()` for it, so this is the only place that fact can
    // be handed to `tour/quiet.ts` — which is what keeps the join-request toast
    // off a popover it would sit on top of and take the clicks from. It is also
    // the earliest a store may be touched at all: see the module comment.
    // An unanswered offer counts as running, because the dialog asking the
    // question is modal: a toast that lands behind it is a toast whose buttons
    // cannot be pressed. Without the second half of this, any navigation while
    // the greeting was up would release the hold it had just taken.
    setTourRunning(useTourStore().status === 'running' || offeredTrack.value !== null)
    // The offer holds the screen on its own — there is no tour yet for the
    // route handler to have an opinion about.
    if (maybeOfferTour(to)) return
    controller.handleRouteChange(to)
  })
}
