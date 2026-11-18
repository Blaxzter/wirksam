import { watch } from 'vue'

import type { RouteLocationNormalized, Router } from 'vue-router'

import { DEFAULT_PUBLIC_LOCALE, type PublicLocale, isPublicLocale, publicPageFor } from '@/lib/seo'

/** Whether the route sits in the public shell, i.e. has a `/de/…` twin. */
export function isLocalizedRoute(route: RouteLocationNormalized): boolean {
  return route.matched.some((record) => record.name === 'preauth-layout')
}

/** The locale a route's URL pins, or `null` for a URL without a prefix. */
export function routeLocale(route: RouteLocationNormalized): PublicLocale | null {
  const param = route.params.locale
  return isPublicLocale(param) ? param : null
}

/** The `locale` param that puts a public page into `locale`. */
export function localeParam(locale: string): string {
  return locale === DEFAULT_PUBLIC_LOCALE ? '' : locale
}

/** The two things this needs from the i18n instance; `i18n.global` fits. */
export interface HeadI18n {
  locale: { value: string }
  t: (key: string) => string
}

/** What `meta.noindex` puts into `<head>`. */
export const NOINDEX_CONTENT = 'noindex, nofollow'

function setMeta(name: string, content: string) {
  document.querySelector(`meta[name="${name}"]`)?.setAttribute('content', content)
}

/**
 * Ask search engines to stay off a page, or stop asking. `index.html` ships no
 * robots meta, so removing the one this adds restores the default.
 */
function setNoindex(on: boolean) {
  const existing = document.head.querySelector('meta[name="robots"]')
  if (!on) {
    existing?.remove()
    return
  }
  if (existing) {
    existing.setAttribute('content', NOINDEX_CONTENT)
    return
  }
  const meta = document.createElement('meta')
  meta.name = 'robots'
  meta.content = NOINDEX_CONTENT
  document.head.appendChild(meta)
}

/**
 * Keep the app locale and `<head>` in step with the URL.
 *
 * - On `/de/…` the page is German whatever the visitor chose before, and
 *   leaving it returns to that choice (`fallbackLocale`, normally the stored
 *   preference). A URL without a prefix changes nothing, so somebody whose
 *   browser speaks German still reads `/` in German. Opened from outside the
 *   app they rarely get that far: the prerendered `/` sends them to `/de` before
 *   its first paint (`localeRedirect` in scripts/prerender.mjs).
 * - A public page gets its own title and description from `preauth.seo`, a
 *   route with `meta.titleKey` its own title, and every other page gets back
 *   the ones `index.html` shipped with. The prerendered HTML already carries
 *   them; this is for client-side navigation and for the pages that are not
 *   prerendered. A change of locale in place applies them again.
 * - A route with `meta.noindex` (the guest pages, whose URLs carry a list's
 *   code or lead to someone's sign-ups) asks search engines not to index it or
 *   follow its links.
 */
export function installPageHead(router: Router, i18n: HeadI18n, fallbackLocale: () => string) {
  const defaultTitle = document.title
  const defaultDescription =
    document.querySelector('meta[name="description"]')?.getAttribute('content') ?? ''

  function applyHead(route: RouteLocationNormalized) {
    const page = publicPageFor(route.name)
    if (page) {
      document.title = i18n.t(`preauth.seo.${page.seoKey}.title`)
      setMeta('description', i18n.t(`preauth.seo.${page.seoKey}.description`))
    } else {
      document.title = route.meta.titleKey ? i18n.t(route.meta.titleKey) : defaultTitle
      setMeta('description', defaultDescription)
    }
    setNoindex(route.meta.noindex === true)
  }

  router.afterEach((to, from) => {
    const pinned = routeLocale(to)
    if (pinned) i18n.locale.value = pinned
    else if (routeLocale(from)) i18n.locale.value = fallbackLocale()
    applyHead(to)
  })

  watch(
    () => i18n.locale.value,
    () => applyHead(router.currentRoute.value),
  )
}
