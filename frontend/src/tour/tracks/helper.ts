/**
 * The volunteer's track: one argument, told in four chapters.
 *
 * The argument is the product's own model — *a job is cut into shifts, and a
 * shift is what you take* — and every screen here is evidence for it rather
 * than the subject of a step. That is why the chapters are named after ideas
 * and not after routes:
 *
 *   `yourEvent`    — you are already on some of this event
 *                    (`home`)
 *   `theJobs`      — what a job is, and what the board is showing you
 *                    (`tasks`)
 *   `takingAShift` — open one, see who is on it, take it in a single press
 *                    (`tasks`, then inside `ShiftDetailDialog`)
 *   `keepingTrack` — what you said yes to, and how to be found by the rest
 *                    (`my-bookings`, `availability`, back to `home`)
 *
 * Nine steps across four routes, all four of which `engine.spec.ts`'s memory
 * router already registers.
 *
 * ── Where the welcome went ───────────────────────────────────────────────────
 * The track used to open on a step that said hello while highlighting the page
 * heading, which pointed at a word the visitor could already read and asked for
 * nothing. The greeting is now `SandboxWelcomeDialog.vue`, shown before any of
 * this runs, and it is also where the tour is *offered* rather than started on
 * somebody who never asked for one. So step one here points at something worth
 * pointing at, and every step in the track earns its highlight.
 *
 * ── Why the anchors are small ────────────────────────────────────────────────
 * Every anchor here is a control or a row, never a section wrapper. driver.js
 * chooses a side by asking whether the popover fits *outside* the anchor's own
 * rectangle, and an anchor taller than the viewport answers no on all four
 * sides — at which point driver pins the card to the bottom of the screen, over
 * the hole it has just cut. `tour/placement.ts` clamps its way out of that, but
 * not needing it is better than needing it, so `task-list` became `task-row`
 * and the availability card became its mode picker.
 *
 * ── The one prose-only step ──────────────────────────────────────────────────
 * `jobsIntro` names no element. The engine reads that as "centre the popover
 * and skip anchor resolution", which is exactly the breath this track needs on
 * arrival at a board it has never seen: the vocabulary lands before the first
 * thing is pointed at. It *replaces* a step rather than adding one.
 *
 * Selectors are `data-testid`s that exist in the app today. The tour is not
 * allowed to invent anchors — a step whose anchor never turns up degrades to a
 * centred popover with no highlight, and the visitor is quietly shown a worse
 * first impression than the one being promised.
 */
import { resetTaskBoard } from '@/tour/preconditions'
import { type TourStepContext, defineTrack } from '@/tour/types'

/** The rows and shift chips this track points at only exist in the list view. */
const TASK_LIST = '[data-testid="task-list"]'

/**
 * A chip the visitor can actually be walked into booking.
 *
 * `WeekDayColumns.vue` writes `data-tour-bookable` per chip, false for one that
 * is full, one the visitor is already on, or one in the past. Pointing at any
 * chip at all was the original defect: the seeder's first upcoming shift is
 * also the one it books the guest onto, so the step that says "press Book"
 * highlighted a button that `ShiftDetailDialog` never rendered.
 */
const BOOKABLE_CHIP = '[data-testid^="shift-chip-"][data-tour-bookable="true"]'
const ANY_CHIP = '[data-testid^="shift-chip-"]'

const SHIFT_DIALOG = '[data-testid="dialog-shift-detail"]'

/**
 * The dialog's footer, which is both an anchor and a readiness signal.
 *
 * It is `v-if="resolvedShift"`, and `TasksView` passes a shift *id* rather than
 * a shift, so the footer only exists once `GET /shifts/{id}` has come back —
 * which is precisely the condition the roster and the book button both need.
 * Waiting on the dialog itself would hand driver a card full of skeletons.
 */
const SHIFT_FOOTER = '[data-testid="shift-detail-footer"]'

/**
 * `page-heading` is on the pre-auth shell, the auth shell and every routed view
 * at once, so it is only unambiguous when scoped to the content area.
 *
 * Note that `main-content` is *not* the post-auth shell's alone — `PreAuthLayout`
 * marks its `<main>` the same way, so this selector matches the landing page's
 * hero just as happily. What keeps the two apart is that only one shell is ever
 * mounted, which holds everywhere except in the single flush between a route
 * changing and `RouterView` catching up. `tour/engine.ts` waits that flush out
 * before it reads the DOM; without it, the first step of a demo anchored to the
 * landing page it had just left.
 */
const PAGE_HEADING = '[data-testid="main-content"] [data-testid="page-heading"]'

/**
 * Get a shift dialog on screen, at most once.
 *
 * Shared by the two steps that live inside it, because the engine re-runs
 * `before()` whenever the view remounts underneath a step — and `TasksView`
 * remounts on every filter change, since it mirrors its filters into the query
 * string. The guard comes first for that reason: without it, a remount would
 * click a second chip behind an already-open dialog.
 *
 * The fallback to *any* chip is a last resort for a demo whose seed has
 * drifted. A dialog showing a full shift still reads correctly against copy
 * about who is already on it; no dialog at all reads as broken.
 *
 * Waiting on the footer rather than the dialog is what makes this hook enough
 * on its own — by the time it resolves, both steps' anchors are real, so
 * neither needs an `anchorTimeout`.
 */
async function openShiftDialog({ waitFor }: TourStepContext): Promise<void> {
  if (document.querySelector(SHIFT_DIALOG)) return

  const chip = (await waitFor(BOOKABLE_CHIP)) ?? (await waitFor(ANY_CHIP, { timeout: 800 }))
  chip?.click()
  await waitFor(SHIFT_FOOTER)
}

export const helperTrack = defineTrack('helper', [
  {
    id: 'nextShift',
    chapter: 'yourEvent',
    route: 'home',
    // The card is unconditional — only its `CardContent` branches on there
    // being a shift — so this anchor is there for a visitor the seeder has put
    // on nothing, and the copy still reads.
    element: '[data-testid="dashboard-next-shift"]',
    side: 'bottom',
  },
  {
    id: 'jobsIntro',
    chapter: 'theJobs',
    route: 'tasks',
    // No `element`: the engine centres the popover and resolves no anchor. The
    // board is behind it, undimmed at the usual overlay opacity, which is the
    // point — the words are about what is already on screen.
    waitFor: TASK_LIST,
    before: () => resetTaskBoard(),
  },
  {
    id: 'jobRow',
    chapter: 'theJobs',
    route: 'tasks',
    element: '[data-testid="task-row"]',
    waitFor: TASK_LIST,
    side: 'bottom',
    // Repeated from the step before, because a visitor who arrives here by Back
    // — or after `TasksView` has mirrored a filter into the query string and
    // remounted — has to land on the same board the copy describes.
    before: () => resetTaskBoard(),
  },
  {
    id: 'openChip',
    chapter: 'takingAShift',
    route: 'tasks',
    element: BOOKABLE_CHIP,
    waitFor: TASK_LIST,
    side: 'right',
  },
  {
    id: 'shiftRoster',
    chapter: 'takingAShift',
    route: 'tasks',
    element: '[data-testid="shift-roster"]',
    // Below `sm` the dialog is a bottom sheet, and the roster fills most of it
    // — there is nowhere left to put a card beside it. The title is a one-line
    // anchor at the top of the same sheet, so the popover has the whole of the
    // screen above to sit in and the roster stays visible underneath.
    mobileElement: '[data-testid="shift-detail-title"]',
    waitFor: SHIFT_FOOTER,
    inOverlay: true,
    side: 'top',
    before: openShiftDialog,
  },
  {
    id: 'bookIt',
    chapter: 'takingAShift',
    route: 'tasks',
    // The footer rather than `btn-book-shift` itself: the copy invites the
    // visitor to press it, and `handleBook` closes the dialog, so an anchor on
    // the button is a rectangle that can vanish mid-step. The footer goes with
    // it, but the engine watches for that (`observeAnchorRemoval`) and re-runs
    // the step centred, which is only honest if the copy was never about one
    // particular button.
    element: SHIFT_FOOTER,
    waitFor: SHIFT_FOOTER,
    inOverlay: true,
    side: 'top',
    align: 'end',
    before: openShiftDialog,
  },
  {
    id: 'myBookings',
    chapter: 'keepingTrack',
    route: 'my-bookings',
    // The view defaults to upcoming only; the copy is about both halves of the
    // screen. `MyBookingsView` reads this and widens its window backwards — a
    // step's `query` can only carry static strings, so the view has to be the
    // one that knows what "all" means in dates.
    query: { range: 'all' },
    element: '[data-testid="booking-card"]',
    waitFor: PAGE_HEADING,
    side: 'top',
  },
  {
    id: 'availability',
    chapter: 'keepingTrack',
    route: 'availability',
    // Rendered twice — a card row from `sm` up and a segmented control below it
    // — under the same testid, with the hidden twin still measurable at zero
    // size. The engine takes the first match that has a real box, so one
    // selector covers both.
    element: '[data-testid="availability-mode-picker"]',
    waitFor: PAGE_HEADING,
    side: 'bottom',
  },
  {
    id: 'finish',
    chapter: 'keepingTrack',
    route: 'home',
    element: '[data-testid="dashboard-quick-actions"]',
    side: 'top',
  },
])
