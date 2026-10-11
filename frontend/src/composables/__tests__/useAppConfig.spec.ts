// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'

import { isSwitchOn, useAppConfig } from '@/composables/useAppConfig'

/**
 * `window.__APP_CONFIG__` is injected at deploy time, so it is absent in dev and
 * in every test run. The fallbacks are what stop the impressum rendering
 * "undefined" as a legal address, which makes them the branch worth pinning.
 *
 * Note that "fallback" does not mean "empty": `SANDBOX_ENABLED` defaults to on,
 * because the value that keeps a deployment working differs per field.
 */
const DEFAULTS = {
  LEGAL_NAME: '',
  LEGAL_ADDRESS: '',
  LEGAL_CITY: '',
  LEGAL_EMAIL: '',
  LEGAL_PHONE: '',
  TURNSTILE_SITE_KEY: '',
  SANDBOX_ENABLED: 'true',
  LANDING_ENABLED: 'true',
}

afterEach(() => {
  delete window.__APP_CONFIG__
})

describe('useAppConfig', () => {
  it('falls back to the defaults when nothing was injected', () => {
    expect(useAppConfig()).toEqual(DEFAULTS)
  })

  it('returns the injected config when the deploy provided one', () => {
    const injected = {
      LEGAL_NAME: 'WirkSam e.V.',
      LEGAL_ADDRESS: 'Musterstraße 1',
      LEGAL_CITY: '12345 Musterstadt',
      LEGAL_EMAIL: 'kontakt@example.org',
      LEGAL_PHONE: '+49 123 456789',
      TURNSTILE_SITE_KEY: '0x4AAAAAAA',
      SANDBOX_ENABLED: 'false',
      LANDING_ENABLED: 'false',
    }
    window.__APP_CONFIG__ = injected

    expect(useAppConfig()).toEqual(injected)
  })

  it('fills in keys an older config.js predates', () => {
    // The realistic shape of a stale deploy: a config written before Turnstile
    // and before the demo existed. Every field it does carry has to survive,
    // and the ones it does not have to read as something safe rather than as
    // `undefined` — which would render a widget against a broken key and wedge
    // the register form, and (for the demo flag) throw on `.toLowerCase()`.
    window.__APP_CONFIG__ = { LEGAL_NAME: 'WirkSam e.V.' }

    expect(useAppConfig()).toEqual({ ...DEFAULTS, LEGAL_NAME: 'WirkSam e.V.' })
  })

  it('leaves the demo switched on for a config that never mentions it', () => {
    window.__APP_CONFIG__ = { TURNSTILE_SITE_KEY: '0x4AAAAAAA' }

    expect(useAppConfig().SANDBOX_ENABLED).toBe('true')
  })

  it('reads the global on every call rather than caching it', () => {
    expect(useAppConfig().LEGAL_NAME).toBe('')

    window.__APP_CONFIG__ = { ...DEFAULTS, LEGAL_NAME: 'Set later' }

    expect(useAppConfig().LEGAL_NAME).toBe('Set later')
  })
})

describe('isSwitchOn', () => {
  it('is off only for the word false, in any case and with stray spaces', () => {
    expect(isSwitchOn('false')).toBe(false)
    expect(isSwitchOn(' FALSE ')).toBe(false)
    expect(isSwitchOn(false)).toBe(false)
  })

  it('stays on for anything else, including a switch that was never set', () => {
    expect(isSwitchOn('true')).toBe(true)
    expect(isSwitchOn('yes')).toBe(true)
    expect(isSwitchOn('')).toBe(true)
    expect(isSwitchOn(undefined)).toBe(true)
  })
})
