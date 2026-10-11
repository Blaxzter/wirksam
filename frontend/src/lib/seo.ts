/**
 * What the outside world can find: the public pages, their URLs per language,
 * and the copy that describes them to search engines and LLM crawlers.
 *
 * Shared by the running app (`installPageHead` keeps `<title>` and the meta
 * description in step on client-side navigation) and by the build-time
 * prerender (`scripts/prerender.mjs`), which writes the same pages out as static
 * HTML together with the sitemap and `llms.txt`. One list, so a page added here
 * shows up in all of them.
 */

export const PUBLIC_LOCALES = ['en', 'de'] as const
export type PublicLocale = (typeof PUBLIC_LOCALES)[number]

/** Served without a prefix. Every other locale lives under `/<locale>/…`. */
export const DEFAULT_PUBLIC_LOCALE: PublicLocale = 'en'

export interface PublicPage {
  /** Route name in `router/routes.ts`. */
  routeName: string
  /** Path without the locale prefix. */
  path: string
  /** Key under `preauth.seo` holding `title` and `description`. */
  seoKey: string
  /**
   * Whether the build writes this page out as static HTML. Privacy and the
   * impressum are left to the SPA: both print the operator's name and address
   * from runtime config, which a build shared by every deployment cannot know.
   */
  prerender: boolean
  changefreq: 'weekly' | 'monthly' | 'yearly'
  priority: number
  /**
   * The runtime switch this page exists under. With it off the page is neither
   * prerendered nor in the sitemap, and the router sends its URL elsewhere.
   */
  requires?: 'LANDING_ENABLED'
}

export const PUBLIC_PAGES: readonly PublicPage[] = [
  {
    routeName: 'landing',
    path: '/',
    seoKey: 'landing',
    prerender: true,
    changefreq: 'monthly',
    priority: 1,
    requires: 'LANDING_ENABLED',
  },
  {
    routeName: 'preauth-changelog',
    path: '/changelog',
    seoKey: 'changelog',
    prerender: true,
    changefreq: 'weekly',
    priority: 0.5,
  },
  {
    routeName: 'terms',
    path: '/terms',
    seoKey: 'terms',
    prerender: true,
    changefreq: 'yearly',
    priority: 0.3,
  },
  {
    routeName: 'privacy',
    path: '/privacy',
    seoKey: 'privacy',
    prerender: false,
    changefreq: 'yearly',
    priority: 0.3,
  },
  {
    routeName: 'impressum',
    path: '/impressum',
    seoKey: 'impressum',
    prerender: false,
    changefreq: 'yearly',
    priority: 0.2,
  },
]

/** The FAQ on the landing page, in display order. `demo` only shows while the demo is offered. */
export const FAQ_KEYS = [
  'what',
  'audience',
  'cost',
  'account',
  'visibility',
  'reminders',
  'calendar',
  'reuse',
  'data',
  'demo',
  'languages',
  'selfHost',
] as const

export function faqKeys(demoEnabled: boolean): readonly (typeof FAQ_KEYS)[number][] {
  return demoEnabled ? FAQ_KEYS : FAQ_KEYS.filter((key) => key !== 'demo')
}

export function isPublicLocale(value: unknown): value is PublicLocale {
  return PUBLIC_LOCALES.includes(value as PublicLocale)
}

/** `/privacy` + `de` → `/de/privacy`; the default locale keeps the bare path. */
export function localizedPath(path: string, locale: PublicLocale): string {
  if (locale === DEFAULT_PUBLIC_LOCALE) return path
  return path === '/' ? `/${locale}` : `/${locale}${path}`
}

export function publicPageFor(routeName: unknown): PublicPage | undefined {
  return PUBLIC_PAGES.find((page) => page.routeName === routeName)
}
