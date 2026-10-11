/**
 * Server-side entry for the build-time prerender (`scripts/prerender.mjs`).
 *
 * Renders one public page to an HTML string with the real components, route
 * table and translations, so what a crawler reads is what a visitor sees. It
 * deliberately leaves out `App.vue` and everything `main.ts` wires up — the
 * session restore, the tour, toasts — because none of it exists for a visitor
 * who has not run any JavaScript yet. In the browser, `main.ts` mounts the app
 * as usual and replaces this markup once it is ready.
 */
import { createSSRApp, h } from 'vue'

import { createPinia } from 'pinia'
import { RouterView, createMemoryHistory, createRouter } from 'vue-router'
import { renderToString } from 'vue/server-renderer'

import type { AppConfig } from '@/composables/useAppConfig'

import type { PublicLocale } from '@/lib/seo'
import i18n from '@/locales/i18n'
import { createRoutes } from '@/router/routes'

export { default as i18n } from '@/locales/i18n'
// The prerender script is plain JavaScript and reads the shared page list from
// here instead of importing TypeScript itself.
export {
  DEFAULT_PUBLIC_LOCALE,
  PUBLIC_LOCALES,
  PUBLIC_PAGES,
  faqKeys,
  localizedPath,
} from '@/lib/seo'

/**
 * `config` stands in for the `config.js` a deployment writes, so each
 * combination of runtime switches renders the page that deployment would show.
 */
export async function render(
  url: string,
  locale: PublicLocale,
  config: Partial<AppConfig>,
): Promise<string> {
  globalThis.__APP_CONFIG__ = config
  i18n.global.locale.value = locale

  const router = createRouter({
    history: createMemoryHistory(),
    routes: createRoutes(() => true),
  })
  const app = createSSRApp({ render: () => h(RouterView) })
  // Vue logs a render error and carries on with a hole in the page. A hole in
  // the page is exactly what crawlers would then index, so fail the build.
  app.config.errorHandler = (error) => {
    throw error
  }
  app.use(createPinia())
  app.use(router)
  app.use(i18n)

  await router.push(url)
  await router.isReady()

  return renderToString(app)
}
