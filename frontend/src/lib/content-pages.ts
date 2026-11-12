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
 *
 * A new feature page or guide is an entry in `DOC_PAGES` and in a group below
 * it, its Markdown in `src/docs/<locale>/`, and its name and search copy under
 * `preauth.docs.pages.<key>` and `preauth.seo.<key>`. Routes and the public page
 * list follow from `DOC_PAGES`.
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

/** Feature pages explain what something does, guides how to set it up, step by step. */
export type DocKind = 'feature' | 'guide'

export interface DocPage {
  kind: DocKind
  /** The last part of the URL, and the Markdown file's name. */
  slug: string
  /** Key under `preauth.seo` and `preauth.docs.pages`. */
  key: string
}

export const DOC_PAGES = [
  { kind: 'feature', slug: 'shift-planning', key: 'featureShiftPlanning' },
  { kind: 'feature', slug: 'venue-map', key: 'featureVenueMap' },
  { kind: 'feature', slug: 'members', key: 'featureMembers' },
  { kind: 'feature', slug: 'people-in-charge', key: 'featurePeopleInCharge' },
  { kind: 'feature', slug: 'teams', key: 'featureTeams' },
  { kind: 'feature', slug: 'booking', key: 'featureBooking' },
  { kind: 'feature', slug: 'notifications', key: 'featureNotifications' },
  { kind: 'feature', slug: 'vouchers', key: 'featureVouchers' },
  { kind: 'feature', slug: 'hours-and-reports', key: 'featureHoursAndReports' },
  { kind: 'feature', slug: 'self-hosting', key: 'featureSelfHosting' },
  { kind: 'guide', slug: 'first-event', key: 'guideFirstEvent' },
  { kind: 'guide', slug: 'volunteer-start', key: 'guideVolunteerStart' },
  { kind: 'guide', slug: 'people-in-charge', key: 'guidePeopleInCharge' },
  { kind: 'guide', slug: 'vouchers', key: 'guideVouchers' },
  { kind: 'guide', slug: 'redeem-vouchers', key: 'guideRedeemVouchers' },
  { kind: 'guide', slug: 'teams', key: 'guideTeams' },
  { kind: 'guide', slug: 'venue-map', key: 'guideVenueMap' },
  { kind: 'guide', slug: 'next-year', key: 'guideNextYear' },
] as const satisfies readonly DocPage[]

/** `feature/vouchers`, how a page is named in `related` and in the Markdown glob. */
export const docId = (page: DocPage) => `${page.kind}/${page.slug}`

export const docRouteName = (page: DocPage) => `${page.kind}-${page.slug}`

export const docPath = (page: DocPage) =>
  `/${page.kind === 'feature' ? 'features' : 'guides'}/${page.slug}`

export function docPageById(id: string): DocPage | undefined {
  return DOC_PAGES.find((page) => docId(page) === id)
}

/** The overview pages, in display order. Keys under `preauth.docs.groups`. */
export const DOC_GROUPS = {
  feature: [
    { key: 'plan', pages: ['feature/shift-planning', 'feature/venue-map'] },
    { key: 'people', pages: ['feature/members', 'feature/people-in-charge', 'feature/teams'] },
    { key: 'volunteers', pages: ['feature/booking', 'feature/notifications'] },
    { key: 'thanks', pages: ['feature/vouchers', 'feature/hours-and-reports'] },
    { key: 'run', pages: ['feature/self-hosting'] },
  ],
  guide: [
    { key: 'start', pages: ['guide/first-event', 'guide/volunteer-start'] },
    { key: 'share', pages: ['guide/people-in-charge', 'guide/teams', 'guide/venue-map'] },
    { key: 'thanks', pages: ['guide/vouchers', 'guide/redeem-vouchers'] },
    { key: 'again', pages: ['guide/next-year'] },
  ],
} as const satisfies Record<DocKind, readonly { key: string; pages: readonly string[] }[]>

/**
 * The colour a page is drawn in. Each is one of the chart colours, which are
 * tuned for both themes. It tints the header, the picture, the summary and the
 * markers on the page; text stays in the theme's own colours, so it never
 * decides whether something is readable.
 */
export type Accent = 'green' | 'orange' | 'amber' | 'blue'

export const ACCENT_COLORS: Readonly<Record<Accent, string>> = {
  green: 'var(--chart-1)',
  orange: 'var(--chart-2)',
  amber: 'var(--chart-3)',
  blue: 'var(--chart-4)',
}

/**
 * A feature page or guide takes the colour of its group, so a group looks the
 * same on the overview and on each of its pages.
 */
export const GROUP_ACCENTS: Readonly<Record<DocKind, Readonly<Record<string, Accent>>>> = {
  feature: { plan: 'green', people: 'orange', volunteers: 'blue', thanks: 'amber', run: 'green' },
  guide: { start: 'green', share: 'orange', thanks: 'amber', again: 'blue' },
}

/**
 * The drawing beside a page's title, see `components/content/PageArt.vue`.
 * `roster` is the roster board from the landing page.
 */
export type ArtKind =
  | 'roster'
  | 'shifts'
  | 'venue'
  | 'members'
  | 'inCharge'
  | 'teams'
  | 'booking'
  | 'notify'
  | 'vouchers'
  | 'reports'
  | 'terminal'
  | 'clone'
  | 'steps'
  | 'festival'
  | 'compare'

/** By id for a feature page or guide, by copy key for a page that stands alone. */
export const PAGE_ART: Readonly<Record<string, ArtKind>> = {
  features: 'roster',
  guides: 'steps',
  alternatives: 'compare',
  clubFestival: 'festival',
  'feature/shift-planning': 'shifts',
  'feature/venue-map': 'venue',
  'feature/members': 'members',
  'feature/people-in-charge': 'inCharge',
  'feature/teams': 'teams',
  'feature/booking': 'booking',
  'feature/notifications': 'notify',
  'feature/vouchers': 'vouchers',
  'feature/hours-and-reports': 'reports',
  'feature/self-hosting': 'terminal',
  'guide/first-event': 'shifts',
  'guide/volunteer-start': 'booking',
  'guide/people-in-charge': 'inCharge',
  'guide/vouchers': 'vouchers',
  'guide/redeem-vouchers': 'vouchers',
  'guide/teams': 'teams',
  'guide/venue-map': 'venue',
  'guide/next-year': 'clone',
}

/** The colour of a page that stands alone, by the same key as in `PAGE_ART`. */
export const PAGE_ACCENTS: Readonly<Record<string, Accent>> = {
  features: 'green',
  guides: 'amber',
  alternatives: 'blue',
  clubFestival: 'orange',
}

/** The colour of a feature page or guide: its group's. */
export function docAccent(id: string): Accent {
  const page = docPageById(id)
  if (!page) return 'green'
  const group = DOC_GROUPS[page.kind].find((item) =>
    (item.pages as readonly string[]).includes(id),
  )
  return (group && GROUP_ACCENTS[page.kind][group.key]) ?? 'green'
}

/** What a page looks like: its drawing and its colour, as a CSS value. */
export function pageLook(key: string): { art?: ArtKind; color: string } {
  const accent = docPageById(key) ? docAccent(key) : (PAGE_ACCENTS[key] ?? 'green')
  return { art: PAGE_ART[key], color: ACCENT_COLORS[accent] }
}

/** What the terminal beside the self-hosting page's title types out: the page's own commands. */
export const TERMINAL_COMMANDS: readonly string[] = [
  'git clone https://github.com/Blaxzter/wirksam.git',
  'cd wirksam',
  'cp .env.example .env',
  'docker compose -f docker-compose.yml up -d --build',
]

/** The cross-links at the foot of a content page; route names and copy keys. */
export const RELATED_PAGES = [
  { routeName: 'features', key: 'features' },
  { routeName: 'guides', key: 'guides' },
  { routeName: 'alternatives', key: 'alternatives' },
  { routeName: 'use-case-club-festival', key: 'clubFestival' },
  { routeName: 'landing', key: 'landing' },
] as const

/** Every related page except the one being read. */
export function relatedPages(currentRouteName: unknown) {
  return RELATED_PAGES.filter((page) => page.routeName !== currentRouteName)
}
