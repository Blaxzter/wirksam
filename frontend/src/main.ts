import { createApp, nextTick } from 'vue'

import { createPinia } from 'pinia'

import { client } from '@/client/client.gen'
import { authSession } from '@/lib/auth-session'
import { installPageHead } from '@/lib/page-head'
import i18n, { detectLocale } from '@/locales/i18n.ts'
import { installFakeSession } from '@/testing/fake-session'
import { installTour } from '@/tour/install'

import App from './App.vue'
import './index.css'
import router from './router'

client.setConfig({
  baseURL: import.meta.env.VITE_API_URL,
  throwOnError: true, // Always throw errors instead of returning them
  // The refresh token lives in an httpOnly cookie, and a browser only attaches
  // cookies to a cross-origin request when it is asked to — which in
  // development every request is (:5555 to :8787). Without this the cookie is
  // simply never sent, `/auth/refresh` sees an anonymous caller, and every
  // reload signs the user out.
  withCredentials: true,
})

const app = createApp(App)

// E2E runs against a backend in TESTING mode that takes identity from the
// X-Test-User-Email header, so the browser half only has to *look* signed in.
// Double-gated on purpose: the build flag alone does nothing, the run has to
// opt in with the cookie as well.
if (import.meta.env.VITE_E2E_AUTH_BYPASS === 'true' && document.cookie.includes('e2e_bypass=1')) {
  installFakeSession()
} else {
  // Restore the session from the refresh cookie. Deliberately not awaited: the
  // app mounts immediately and `App.vue` shows a spinner until this settles,
  // while the route guards await the very same one-shot promise — so nothing is
  // ever decided against a session that has not been restored yet.
  void authSession.bootstrap()
}

app.use(createPinia())
app.use(router)
app.use(i18n)

// Public pages carry their language in the URL (`/de/…`) and their own title.
installPageHead(router, i18n.global, detectLocale)

// The guided tour hangs off `router.afterEach` and a window event, so it has to
// be wired after the router exists and before the first navigation settles.
// Deliberately after i18n as well: the popover reads its copy from the same
// singleton, and after mount would be too late for a tour restored from
// `sessionStorage` by a reload.
installTour(router)

// A public page arrives prerendered (scripts/prerender.mjs) and is readable
// before any of this has run. Mounting straight onto it would swap that page
// for the session spinner and then back, so the static copy moves aside and
// stays on screen until the app has routed and rendered the same page.
const root = document.getElementById('app')!
if (root.hasAttribute('data-prerendered')) {
  const prerendered = document.createElement('div')
  prerendered.append(...root.childNodes)
  // Nothing in it works until the app takes over, so it is inert, hidden from
  // assistive tech, and stripped of test ids — a click or a locator that lands
  // here would otherwise hit a dead copy of the button it was looking for.
  prerendered.inert = true
  prerendered.setAttribute('aria-hidden', 'true')
  prerendered.querySelectorAll('[data-testid]').forEach((el) => el.removeAttribute('data-testid'))
  root.before(prerendered)
  root.removeAttribute('data-prerendered')
  root.hidden = true
  void router
    .isReady()
    .then(() => nextTick())
    .finally(() => {
      prerendered.remove()
      root.hidden = false
    })
}

app.mount(root)

// Register service worker for push notifications
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch((error) => {
    console.warn('Service worker registration failed:', error)
  })
}
