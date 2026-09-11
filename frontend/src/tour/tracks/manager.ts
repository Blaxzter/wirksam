/**
 * The organiser's track: one loop, told in four chapters.
 *
 * The loop is describe a job once → let wirksam cut it into shifts → watch the
 * thin ones → read afterwards how it went, and the chapters are that loop's
 * four beats rather than the four screens it happens to visit:
 *
 *   `whereThingsStand` — what is asking for you this week
 *                        (`home`)
 *   `theJobs`          — what a job is, and how staffing reads at a glance
 *                        (`tasks`)
 *   `buildingAJob`     — the form the whole board came out of
 *                        (`task-create`, prefilled)
 *   `peopleAndNumbers` — who is in it, how it went, back to the start
 *                        (`event-settings`, `reporting`, `home`)
 *
 * Ten steps across five routes.
 *
 * ── Where the welcome went ───────────────────────────────────────────────────
 * The greeting is `SandboxWelcomeDialog.vue` now, shown before this track
 * starts — and it is where the tour is offered rather than started on somebody
 * who never asked. The step it replaced highlighted the page heading, which is
 * a word the visitor can already read; see `tracks/helper.ts` for the longer
 * version of that argument.
 *
 * ── The create form, opened one section at a time ────────────────────────────
 * `TaskCreateView` is a five-section accordion, `type="single" collapsible`, and
 * the copy used to name fields that were folded away. Each of the three form
 * steps now opens its own section through `openSection()` before the anchor is
 * resolved, and opening one closes the last, which is the right motion walking
 * down a form and means no step has to close anything. The hook is
 * `data-state`-guarded, which matters more than it looks: `activeSection` starts
 * on `'details'`, so an unguarded click on an already-open section *collapses*
 * it.
 *
 * The anchors inside the form are the controls the copy is actually about —
 * `input-task-date-mode`, `input-shift-duration`, `preview-summary` — rather
 * than the section wrappers, which are taller than the viewport once open and
 * would send driver.js into pinning the card over its own stage.
 *
 * ── This track's one prose-only step ─────────────────────────────────────────
 * Each track gets exactly one breath, placed where it buys the most. The
 * helper's lands on arrival at a board it has never seen; this one lands on
 * arrival at `task-create`, because the organiser has already read the board's
 * summary on the dashboard and the expensive moment here is the accordion.
 * `formIntro` names no element, so the engine centres it and resolves no
 * anchor — the folding is explained before anything starts rearranging.
 */
import { resetTaskBoard } from '@/tour/preconditions'
import { defineTrack } from '@/tour/types'

const TASK_LIST = '[data-testid="task-list"]'
const PAGE_HEADING = '[data-testid="main-content"] [data-testid="page-heading"]'

/**
 * The same bookable-chip selector the helper track uses.
 *
 * The organiser is being shown how to *read* the chip rather than how to take
 * it, but the requirement is the same one: a chip that is full has no gap in it
 * to point at, and "this one is still short of people" has to be true of the
 * thing under the highlight.
 */
const BOOKABLE_CHIP = '[data-testid^="shift-chip-"][data-tour-bookable="true"]'

/**
 * People, invitations and join requests all live behind one tab of one route.
 *
 * Mandatory rather than tidy: `EventSettingsView`'s `activeTab` defaults to
 * `'details'`, and the three people cards are rendered only under
 * `activeTab === 'people'`, so without this the step points at a tab nobody
 * opened.
 */
const PEOPLE_TAB = { tab: 'people' }

/**
 * Ask `TaskCreateView` to arrive with something in it.
 *
 * The preview section is the climax of this chapter, and an empty form produces
 * `totalShifts === 0` and a "no shifts yet" placeholder where the count should
 * be. The view fills itself in from this flag — gated on the account being a
 * sandbox one — so the three form steps describe a form that has an answer.
 */
const PREFILL = { tour: 'prefill' }

export const managerTrack = defineTrack('manager', [
  {
    id: 'attention',
    chapter: 'whereThingsStand',
    route: 'home',
    // The one conditional anchor in either track: `AttentionStrip` renders
    // nothing when it has nothing to report. The seeder always leaves a pending
    // join request, so for a demo it is there — but the copy is written to read
    // correctly either way, and the short timeout means a well-run real event
    // degrades to a centred popover in a second and a half rather than freezing
    // the tour for the full six.
    element: '[data-testid="dashboard-attention"]',
    anchorTimeout: 1500,
    side: 'bottom',
  },
  {
    id: 'jobRow',
    chapter: 'theJobs',
    route: 'tasks',
    element: '[data-testid="task-row"]',
    waitFor: TASK_LIST,
    side: 'bottom',
    // The organiser's board is at the mercy of the same persisted filters as
    // the volunteer's — `myBookingsOnly` left on by an earlier demo hides every
    // chip the next step needs.
    before: () => resetTaskBoard(),
  },
  {
    id: 'staffing',
    chapter: 'theJobs',
    route: 'tasks',
    element: BOOKABLE_CHIP,
    waitFor: TASK_LIST,
    side: 'right',
    // Repeated, because the engine re-runs `before()` on a remount and
    // `TasksView` remounts whenever it mirrors a filter into the query string.
    before: () => resetTaskBoard(),
  },
  {
    id: 'formIntro',
    chapter: 'buildingAJob',
    route: 'task-create',
    query: PREFILL,
    // No `element`. The wait is on the first section instead, so the popover
    // arrives over a form that has finished mounting rather than over a blank
    // route transition.
    waitFor: '[data-testid="section-task-details"]',
  },
  {
    id: 'taskDates',
    chapter: 'buildingAJob',
    route: 'task-create',
    query: PREFILL,
    element: '[data-testid="input-task-date-mode"]',
    side: 'bottom',
    // Awaited in a block body rather than returned: the engine needs the
    // promise this hook itself returns, and `openSection` resolves with the
    // section element instead. Same shape in the two steps below.
    before: async ({ openSection }) => {
      await openSection('section-task-dates')
    },
  },
  {
    id: 'generateShifts',
    chapter: 'buildingAJob',
    route: 'task-create',
    query: PREFILL,
    element: '[data-testid="input-shift-duration"]',
    side: 'bottom',
    before: async ({ openSection }) => {
      await openSection('section-schedule')
    },
  },
  {
    id: 'shiftPreview',
    chapter: 'buildingAJob',
    route: 'task-create',
    query: PREFILL,
    // The count, not the list under it: the copy is about checking a number
    // before committing to it, and the list of generated shifts is long enough
    // to be taller than the viewport on any event worth previewing.
    element: '[data-testid="preview-summary"]',
    side: 'bottom',
    before: async ({ openSection }) => {
      await openSection('section-preview')
    },
  },
  {
    id: 'people',
    chapter: 'peopleAndNumbers',
    route: 'event-settings',
    query: PEOPLE_TAB,
    // One row rather than the members card: the copy is about what a row says
    // about a person, and it can point at the join request above and the
    // invitation card below without having to anchor on either.
    element: '[data-testid="event-member-row"]',
    waitFor: PAGE_HEADING,
    side: 'bottom',
  },
  {
    id: 'reporting',
    chapter: 'peopleAndNumbers',
    route: 'reporting',
    // The fill-rate tile is the one number this step is arguing for; the
    // overview grid it sits in is what has to have rendered first.
    element: '[data-testid="stat-fill-rate"]',
    waitFor: '[data-testid="section-overview"]',
    side: 'bottom',
  },
  {
    id: 'finish',
    chapter: 'peopleAndNumbers',
    route: 'home',
    element: '[data-testid="dashboard-quick-actions"]',
    side: 'top',
  },
])
