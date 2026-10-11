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

function setMeta(name: string, content: string) {
  document.querySelector(`meta[name="${name}"]`)?.setAttribute('content', content)
}

/**
 * Keep the app locale and `<head>` in step with the URL.
 *
 * - On `/de/…` the page is German whatever the visitor chose before, and
 *   leaving it returns to that choice (`fallbackLocale`, normally the stored
 *   preference). A URL without a prefix changes nothing, so somebody whose
 *   browser speaks German still reads `/` in German.
 * - A public page gets its own title and description from `preauth.seo`, and
 *   every other page gets back the ones `index.html` shipped with. The
 *   prerendered HTML already carries them; this is for client-side navigation
 *   and for the pages that are not prerendered.
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
      document.title = defaultTitle
      setMeta('description', defaultDescription)
    }
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
