/**
 * The organiser's track: one loop, told in four chapters.
 *
 * The loop is describe a job once → let wirksam cut it into shifts → watch the
 * thin ones → read afterwards how it went, and the chapters are that loop's
 * four beats rather than the four screens it happens to visit:
 *
 *   `whereThingsStand` — what is asking for you this week
 *                        (`home`)
 *   `theJobs`          — what a job is, how staffing reads at a glance, and
 *                        where a new one starts
 *                        (`tasks`)
 *   `buildingAJob`     — the form the whole board came out of, one control at
 *                        a time
 *                        (`task-create`, prefilled)
 *   `peopleAndNumbers` — who is in it, how it went, back to the start
 *                        (`event-settings`, `reporting`, `home`)
 *
 * Twenty-two steps across five routes.
 *
 * ── One element per step ─────────────────────────────────────────────────────
 * The track used to explain a screen from one highlight: a single step named
 * the daily window, the shift length and the head count while pointing at the
 * length alone, and another described the join request, the member list and
 * the invitation card from one member row. Each of those is its own step now,
 * anchored on the control the words are about. Consecutive steps on one route
 * cost no navigation — the engine only moves the highlight — so the extra
 * steps are cheap to walk through.
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
 * the copy used to name fields that were folded away. Each form step opens its
 * own section through `openSection()` before the anchor is resolved, and
 * opening one closes the last, which is the right motion walking down a form
 * and means no step has to close anything. The hook is `data-state`-guarded,
 * which matters more than it looks: `activeSection` starts on `'details'`, so
 * an unguarded click on an already-open section *collapses* it — and several
 * steps in a row now share a section.
 *
 * The anchors inside the form are the controls the copy is actually about —
 * `input-task-date-mode`, `input-shift-duration`, `preview-summary` — rather
 * than the section wrappers, which are taller than the viewport once open and
 * would send driver.js into pinning the card over its own stage. The same goes
 * for the preview list: `preview-day` is the first day of it, not all of them.
 *
 * The event section is the one the tour walks past. The prefill has already
 * chosen the demo's event, `formIntro` says so, and a step pointing at a
 * settled radio button would ask the visitor to read a choice nobody is making.
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
import { type TourStepContext, defineTrack } from '@/tour/types'

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
 * sandbox one — so the form steps describe a form that has an answer.
 */
const PREFILL = { tour: 'prefill' }

/**
 * A `before()` hook that opens one form section.
 *
 * Awaited in a block body rather than returned: the engine needs the promise
 * this hook itself returns, and `openSection` resolves with the section element
 * instead.
 */
function inSection(testId: string) {
  return async ({ openSection }: TourStepContext): Promise<void> => {
    await openSection(testId)
  }
}

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
    id: 'jobInfo',
    chapter: 'theJobs',
    route: 'tasks',
    // The job half of the first row: the copy is about what an organiser
    // describes once, and the day columns beside it are what wirksam made of it.
    element: '[data-testid="task-row-info"]',
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
    id: 'newJob',
    chapter: 'theJobs',
    route: 'tasks',
    // The header button exists from `xl` up and the floating one below it,
    // which is not the engine's `md` split — so this is a preference, and the
    // engine falls back to whichever of the two actually has a box.
    element: '[data-testid="btn-create-task"]',
    mobileElement: '[data-testid="fab-create-task"]',
    waitFor: TASK_LIST,
    side: 'bottom',
    align: 'end',
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
    id: 'taskDetails',
    chapter: 'buildingAJob',
    route: 'task-create',
    query: PREFILL,
    // The name field, the first of the four the section holds: a short anchor
    // at the top of it, so the card can sit below and the rest stays readable.
    element: '[data-testid="input-task-name"]',
    side: 'bottom',
    before: inSection('section-task-details'),
  },
  {
    id: 'taskDates',
    chapter: 'buildingAJob',
    route: 'task-create',
    query: PREFILL,
    element: '[data-testid="input-task-date-mode"]',
    side: 'bottom',
    before: inSection('section-task-dates'),
  },
  {
    id: 'dailyWindow',
    chapter: 'buildingAJob',
    route: 'task-create',
    query: PREFILL,
    element: '[data-testid="input-daily-window"]',
    side: 'bottom',
    before: inSection('section-schedule'),
  },
  {
    id: 'shiftLength',
    chapter: 'buildingAJob',
    route: 'task-create',
    query: PREFILL,
    element: '[data-testid="input-shift-duration"]',
    side: 'bottom',
    before: inSection('section-schedule'),
  },
  {
    id: 'peoplePerShift',
    chapter: 'buildingAJob',
    route: 'task-create',
    query: PREFILL,
    element: '[data-testid="input-people-per-shift"]',
    side: 'bottom',
    before: inSection('section-schedule'),
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
    before: inSection('section-preview'),
  },
  {
    id: 'excludeShift',
    chapter: 'buildingAJob',
    route: 'task-create',
    query: PREFILL,
    // One day of the list — the first match — for the reason above.
    element: '[data-testid="preview-day"]',
    side: 'top',
    before: inSection('section-preview'),
  },
  {
    id: 'saveJob',
    chapter: 'buildingAJob',
    route: 'task-create',
    query: PREFILL,
    element: '[data-testid="btn-submit"]',
    side: 'top',
    align: 'end',
    before: inSection('section-preview'),
  },
  {
    id: 'joinRequest',
    chapter: 'peopleAndNumbers',
    route: 'event-settings',
    query: PEOPLE_TAB,
    // The seeder leaves one pending request for the manager variant. A visitor
    // who answered it from the dashboard has none left, and the step then
    // degrades to a centred card whose copy still reads.
    element: '[data-testid="join-request-row"]',
    waitFor: PAGE_HEADING,
    anchorTimeout: 3000,
    side: 'bottom',
  },
  {
    id: 'people',
    chapter: 'peopleAndNumbers',
    route: 'event-settings',
    query: PEOPLE_TAB,
    // One row rather than the members card: the copy is about what a row says
    // about a person.
    element: '[data-testid="event-member-row"]',
    waitFor: PAGE_HEADING,
    side: 'bottom',
  },
  {
    id: 'memberHours',
    chapter: 'peopleAndNumbers',
    route: 'event-settings',
    query: PEOPLE_TAB,
    element: '[data-testid="section-event-hours"]',
    waitFor: PAGE_HEADING,
    side: 'top',
  },
  {
    id: 'invitations',
    chapter: 'peopleAndNumbers',
    route: 'event-settings',
    query: PEOPLE_TAB,
    element: '[data-testid="section-event-invitations"]',
    waitFor: PAGE_HEADING,
    side: 'top',
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
    id: 'topVolunteers',
    chapter: 'peopleAndNumbers',
    route: 'reporting',
    // Both charts are `v-if` on having data. The seeded history always gives
    // them some, so the short wait is for a real event that has none yet.
    element: '[data-testid="chart-top-volunteers"]',
    waitFor: '[data-testid="section-overview"]',
    anchorTimeout: 1500,
    side: 'top',
  },
  {
    id: 'busiestTimes',
    chapter: 'peopleAndNumbers',
    route: 'reporting',
    element: '[data-testid="chart-busiest-times"]',
    waitFor: '[data-testid="section-overview"]',
    anchorTimeout: 1500,
    side: 'top',
  },
  {
    id: 'export',
    chapter: 'peopleAndNumbers',
    route: 'reporting',
    // Below `sm` the export sits in an overflow menu; its trigger is the
    // closest thing on screen to the button the copy names.
    element: '[data-testid="btn-export"]',
    mobileElement: '[data-testid="btn-export-menu"]',
    waitFor: '[data-testid="section-overview"]',
    side: 'bottom',
    align: 'end',
  },
  {
    id: 'finish',
    chapter: 'peopleAndNumbers',
    route: 'home',
    element: '[data-testid="dashboard-quick-actions"]',
    side: 'top',
  },
])
