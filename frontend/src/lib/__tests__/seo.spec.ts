import { describe, expect, it } from 'vitest'

import dePreauth from '@/locales/de/preauth.json'
import enPreauth from '@/locales/en/preauth.json'

import {
  FAQ_KEYS,
  PUBLIC_PAGES,
  faqKeys,
  isPublicLocale,
  localizedPath,
  publicPageFor,
} from '../seo'

describe('localizedPath', () => {
  it('leaves the default locale unprefixed', () => {
    expect(localizedPath('/', 'en')).toBe('/')
    expect(localizedPath('/terms', 'en')).toBe('/terms')
  })

  it('prefixes every other locale, without a trailing slash on the root', () => {
    expect(localizedPath('/', 'de')).toBe('/de')
    expect(localizedPath('/terms', 'de')).toBe('/de/terms')
  })
})

describe('isPublicLocale', () => {
  it('accepts the public locales only', () => {
    expect(isPublicLocale('en')).toBe(true)
    expect(isPublicLocale('de')).toBe(true)
    expect(isPublicLocale('fr')).toBe(false)
    expect(isPublicLocale(undefined)).toBe(false)
    expect(isPublicLocale(['de'])).toBe(false)
  })
})

describe('publicPageFor', () => {
  it('finds a page by route name', () => {
    expect(publicPageFor('terms')?.path).toBe('/terms')
  })

  it('answers undefined for an app route', () => {
    expect(publicPageFor('home')).toBeUndefined()
    expect(publicPageFor(undefined)).toBeUndefined()
  })
})

describe('faqKeys', () => {
  it('lists every question while the demo is offered', () => {
    expect(faqKeys(true)).toEqual(FAQ_KEYS)
  })

  it('drops the demo question when the demo is switched off', () => {
    expect(faqKeys(false)).not.toContain('demo')
    expect(faqKeys(false)).toHaveLength(FAQ_KEYS.length - 1)
  })
})

// The prerender, the sitemap and llms.txt all read these keys; a missing one
// would surface as a raw key path in a search result.
describe.each([
  ['en', enPreauth],
  ['de', dePreauth],
])('%s copy', (_locale, messages) => {
  it.each(PUBLIC_PAGES.map((page) => page.seoKey))('has a title and description for %s', (key) => {
    const seo = messages.seo[key as keyof typeof messages.seo]
    expect(seo.title).toBeTruthy()
    expect(seo.description).toBeTruthy()
    // vue-i18n reads `|` as a plural separator: "Changelog | WirkSam" renders
    // as "Changelog".
    expect(seo.title).not.toContain('|')
    expect(seo.description).not.toContain('|')
  })

  it.each([...FAQ_KEYS])('has a question and answer for %s', (key) => {
    const item = messages.landing.faq.items[key]
    expect(item.question).toBeTruthy()
    expect(item.answer).toBeTruthy()
  })
})
