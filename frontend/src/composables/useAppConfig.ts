interface AppConfig {
  LEGAL_NAME: string
  LEGAL_ADDRESS: string
  LEGAL_CITY: string
  LEGAL_EMAIL: string
  LEGAL_PHONE: string
  /** Cloudflare Turnstile site key. Empty means the bot check is switched off. */
  TURNSTILE_SITE_KEY: string
  /**
   * Whether the "try a demo event" entry points are offered.
   *
   * A string, not a boolean: this file describes what `config.js` can actually
   * contain, and `config.js` is written by a shell script substituting an
   * environment variable. Only the literal `'false'` switches the demo off —
   * see `stores/sandbox.ts`, which owns that reading — so an unset variable
   * leaves it on, matching the backend's own `SANDBOX_ENABLED` default.
   */
  SANDBOX_ENABLED: string
  /**
   * Whether `/` shows the landing page. A self-hosted deployment that only
   * wants the app switches it off, and `/` then leads to sign-in or the
   * dashboard; the legal pages and the changelog stay. Read like
   * `SANDBOX_ENABLED`, see `isSwitchOn`.
   */
  LANDING_ENABLED: string
}

declare global {
  // A global rather than a `Window` property: in the browser `config.js` sets
  // it on `window`, which is the global object, and the build-time prerender
  // sets it on Node's global object to render the page each deployment would.
  var __APP_CONFIG__: Partial<AppConfig> | undefined
}

/**
 * Runtime configuration, read fresh from `window.__APP_CONFIG__` on every call.
 *
 * `public/config.js` holds the development copy and `docker-entrypoint.sh`
 * rewrites it from environment variables before nginx starts — which is what
 * lets one built image serve two deployments with different legal details and
 * different Turnstile keys.
 *
 * The defaults are merged **per field**, not used as an all-or-nothing
 * fallback. A `config.js` written before a key existed is otherwise a perfectly
 * valid object that happens to answer `undefined` for the new one, and the
 * consequences are silent: an impressum reading "undefined", a widget that
 * renders against a broken `TURNSTILE_SITE_KEY` and a registration form nobody
 * can submit, or a `SANDBOX_ENABLED` nobody set that reads as "off" and quietly
 * takes the demo away from a deployment that never asked to lose it.
 *
 * Note that the safe default is not the same in each direction: an empty
 * Turnstile key means "no bot check", while an absent `SANDBOX_ENABLED` means
 * "demo on". Each default is the value that leaves the deployment working.
 */
const DEFAULTS: AppConfig = {
  LEGAL_NAME: '',
  LEGAL_ADDRESS: '',
  LEGAL_CITY: '',
  LEGAL_EMAIL: '',
  LEGAL_PHONE: '',
  TURNSTILE_SITE_KEY: '',
  SANDBOX_ENABLED: 'true',
  LANDING_ENABLED: 'true',
}

export type { AppConfig }

/**
 * How an on/off switch in `config.js` is read: on unless it says `'false'`,
 * ignoring case and spaces. `config.js` is written by a shell script from
 * environment variables, so an unset variable arrives as the `'true'` default
 * and a deploy predating a switch answers `undefined` — both stay on. `String()`
 * because the development copy is hand-edited, and a real boolean `false` there
 * should mean what it looks like. `docker-entrypoint.sh` reads them the same way.
 */
export function isSwitchOn(value: unknown): boolean {
  return (
    String(value ?? 'true')
      .trim()
      .toLowerCase() !== 'false'
  )
}

export function useAppConfig(): AppConfig {
  return { ...DEFAULTS, ...globalThis.__APP_CONFIG__ }
}
