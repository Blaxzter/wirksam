/**
 * View state the tour's copy assumes, made true before a step runs.
 *
 * Everything here is *preparation*, not narration: it puts a screen into the
 * shape the words describe. The tracks reach it through a step's `before()`
 * hook, and every function has to be idempotent, because the engine re-runs
 * those hooks whenever the view remounts underneath a step — which `TasksView`
 * does on every filter change, since it mirrors its filters into the query
 * string with `router.replace`.
 */
import { useTaskFiltersStore } from '@/stores/eventFilters'

/**
 * Put the task board back into the state the tour describes.
 *
 * Every one of these is persisted per browser under `wirksam:tasks:filters`, so
 * it survives an earlier visit, an earlier demo, or a real account on the same
 * machine. Two of them break the tour outright rather than merely looking odd:
 *
 *   `viewMode` — only the list view draws shift chips, so a visitor who last
 *     left the calendar open was walked through three steps that all missed;
 *   `myBookingsOnly` — with it on, every chip on screen is one the visitor has
 *     already booked, which is exactly the set the "take a shift" step must not
 *     open.
 *
 * `hideFullShifts` and the date range are reset one rung down from that: they
 * change which chips exist at all, and the copy talks about a board with gaps
 * in it. (`hideFullShifts` is no longer persisted, but a `?hide_full=true`
 * link, the dashboard's "find a shift", still turns it on.)
 *
 * `focusMode` is `'first-available'` rather than the store's own `'today'`
 * default. Both are valid, but `'today'` can land on a column whose chips are
 * every one of them full, in which case nothing matches
 * `[data-tour-bookable="true"]`, and three consecutive steps degrade to centred
 * popovers. `'first-available'` is what makes the bookable chip a guarantee
 * rather than a hope.
 *
 * Idempotent by construction: every line is an assignment, so a second run
 * changes nothing.
 */
export function resetTaskBoard(): void {
  const filters = useTaskFiltersStore()
  // `resetFilters()` covers searchQuery, myBookingsOnly, hideFullShifts and the
  // two dates, and deliberately leaves the view untouched — it is the button
  // behind "clear filters", where changing the layout under the visitor would
  // be a surprise. The tour wants both, so it says so.
  filters.resetFilters()
  filters.viewMode = 'list'
  filters.focusMode = 'first-available'
}
