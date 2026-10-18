/**
 * The structure of the content pages: the comparison page and the use-case
 * pages. The words live in `preauth.json`; this file only holds what the copy
 * cannot, namely the order of things (the locale files are sorted
 * alphabetically by a hook), which screenshot goes with which step, and the
 * links to outside sources.
 *
 * A new use-case page is an entry in `USE_CASES`, a route in
 * `router/routes.ts`, a page in `lib/seo.ts`, and its copy under
 * `preauth.useCases.<key>` in both locales. `views/preauth/UseCaseView.vue`
 * renders all of them.
 */

export interface UseCaseStep {
  /** Key under `preauth.useCases.<useCase>.steps.items`. */
  key: string
  /** Screenshot basename, see `components/landing/ScreenshotFrame.vue`. */
  screenshot: string
}

export interface UseCase {
  /** Route name in `router/routes.ts`. */
  routeName: string
  /** Keys under `preauth.useCases.<useCase>.pains.items`, in display order. */
  pains: readonly string[]
  steps: readonly UseCaseStep[]
  /** Keys under `preauth.useCases.<useCase>.faq.items`, in display order. */
  faq: readonly string[]
}

export const USE_CASES = {
  clubFestival: {
    routeName: 'use-case-club-festival',
    pains: ['gaps', 'chat', 'noShows', 'teardown', 'versions'],
    steps: [
      { key: 'stands', screenshot: 'shift-schedule' },
      { key: 'setup', screenshot: 'task-detail' },
      { key: 'invite', screenshot: 'availability' },
      { key: 'gaps', screenshot: 'tasks' },
      { key: 'reminders', screenshot: 'notification-preferences' },
      { key: 'nextYear', screenshot: 'clone-event' },
    ],
    faq: ['helperList', 'account', 'headcount', 'setup', 'cancellations', 'share'],
  },
} as const satisfies Record<string, UseCase>

export type UseCaseKey = keyof typeof USE_CASES

/** Answers the use case a route renders, or `undefined` for any other route. */
export function useCaseForRoute(routeName: unknown): UseCaseKey | undefined {
  return (Object.keys(USE_CASES) as UseCaseKey[]).find(
    (key) => USE_CASES[key].routeName === routeName,
  )
}

/** Columns of the comparison table; keys under `preauth.alternatives.criteria`. */
export const COMPARISON_CRITERIA = [
  'price',
  'account',
  'openSource',
  'selfHost',
  'hosting',
  'languages',
  'reminders',
] as const

export interface ComparedTool {
  /** Key under `preauth.alternatives.tools`. */
  key: string
  url: string
  /** Where the facts in the table come from, as checked for `asOf`. */
  sources: readonly string[]
}

/**
 * The tools on the comparison page, WirkSam first. Every fact in the copy has
 * to come from one of these sources; where they say nothing, the cell says so
 * instead of guessing.
 */
export const COMPARED_TOOLS: readonly ComparedTool[] = [
  {
    key: 'wirksam',
    url: 'https://github.com/Blaxzter/wirksam',
    sources: ['https://github.com/Blaxzter/wirksam'],
  },
  {
    key: 'engelsystem',
    url: 'https://engelsystem.de/',
    sources: [
      'https://engelsystem.de/',
      'https://github.com/engelsystem/engelsystem',
      'https://engelsystem.de/doc/admin/configuration/',
    ],
  },
  {
    key: 'helferstube',
    url: 'https://helferstube.de',
    sources: [
      'https://helferstube.de',
      'https://helferstube.de/preise',
      'https://helferstube.de/legal/dse',
    ],
  },
  {
    key: 'helferplanung',
    url: 'https://helferplanung.app',
    sources: [
      'https://helferplanung.app/de/preise',
      'https://helferplanung.app/de/funktionen',
      'https://helferplanung.app/de/datenschutz',
    ],
  },
  {
    key: 'doodle',
    url: 'https://doodle.com',
    sources: [
      'https://doodle.com/en/premium/',
      'https://help.doodle.com/en/articles/9457222-sign-up-sheet-faq',
      'https://help.doodle.com/en/articles/9457187',
      'https://help.doodle.com/en/articles/10308840',
      'https://doodle.com/en/privacy-policy/',
    ],
  },
  {
    key: 'spreadsheet',
    url: 'https://workspace.google.com/products/sheets/',
    sources: [
      'https://support.google.com/docs/answer/2494822?hl=en',
      'https://support.google.com/docs/answer/91588?hl=en',
      'https://support.microsoft.com/en-us/office/share-files-and-folders-in-onedrive-9fcc2f7d-de0c-4cec-93b0-a82024800c07',
      'https://support.microsoft.com/en-us/office/share-a-document-with-no-sign-in-necessary-8d0dc009-4207-4a91-b051-356948579732',
    ],
  },
]

/** Product screenshots on the comparison page, captioned with the landing page's copy. */
export const COMPARISON_SCREENSHOTS = [
  { key: 'overview', screenshot: 'tasks' },
  { key: 'shifts', screenshot: 'shift-schedule' },
  { key: 'bookings', screenshot: 'my-bookings' },
] as const

/** The cross-links at the foot of a content page; route names and copy keys. */
export const RELATED_PAGES = [
  { routeName: 'alternatives', key: 'alternatives' },
  { routeName: 'use-case-club-festival', key: 'clubFestival' },
  { routeName: 'landing', key: 'landing' },
] as const

/** Every related page except the one being read. */
export function relatedPages(currentRouteName: unknown) {
  return RELATED_PAGES.filter((page) => page.routeName !== currentRouteName)
}
