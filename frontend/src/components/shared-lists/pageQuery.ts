/**
 * Where the shared-lists page keeps its state in the address, so a reload or
 * a link someone sends lands on the same tab, view and open list:
 *
 * `?tab=tasks&tasks_filter=todo`, `?tab=preview&preview=<id>`, and on a
 * list's own page `?signups_page=2`. The links table uses the bare keys
 * (`page`, `sort`, `dir`, `q`, `filter`); the other two tables a prefix each.
 */

export const TABS = ['links', 'tasks', 'preview'] as const
export type SharedListsTab = (typeof TABS)[number]

export const TAB_KEY = 'tab'
/** The list whose details were open, back when they were a dialog: now a redirect. */
export const LIST_KEY = 'list'
/** The list the preview tab shows. */
export const PREVIEW_KEY = 'preview'
export const TASKS_PREFIX = 'tasks'
export const SIGNUPS_PREFIX = 'signups'
