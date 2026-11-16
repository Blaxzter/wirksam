// @vitest-environment jsdom
import { nextTick, ref } from 'vue'

import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { type Router, createMemoryHistory, createRouter } from 'vue-router'

import {
  NOINDEX_CONTENT,
  installPageHead,
  isLocalizedRoute,
  localeParam,
  routeLocale,
} from '../page-head'

const Empty = { render: () => null }

function makeRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/:locale(de)?',
        name: 'preauth-layout',
        component: Empty,
        children: [
          { path: '', name: 'landing', component: Empty },
          { path: 'terms', name: 'terms', component: Empty },
        ],
      },
      { path: '/app/home', name: 'home', component: Empty },
      {
        path: '/l/:code',
        name: 'shared-list-public',
        component: Empty,
        meta: { noindex: true, titleKey: 'guestSignup.page.title' },
      },
      {
        path: '/guest-signup',
        name: 'guest-signup-manage',
        component: Empty,
        meta: { noindex: true },
      },
    ],
  })
}

describe('route helpers', () => {
  it('knows which routes have a localized twin', async () => {
    const router = makeRouter()
    await router.push('/de/terms')
    expect(isLocalizedRoute(router.currentRoute.value)).toBe(true)
    expect(routeLocale(router.currentRoute.value)).toBe('de')

    await router.push('/terms')
    expect(routeLocale(router.currentRoute.value)).toBeNull()

    await router.push('/app/home')
    expect(isLocalizedRoute(router.currentRoute.value)).toBe(false)
  })

  it('maps a locale to its URL param', () => {
    expect(localeParam('en')).toBe('')
    expect(localeParam('de')).toBe('de')
  })
})

describe('installPageHead', () => {
  let router: Router
  const locale = ref('en')
  let stored = 'en'
  const t = (key: string) => `${locale.value}:${key}`

  beforeEach(() => {
    document.head.innerHTML =
      '<title>Default title</title><meta name="description" content="Default description">'
    locale.value = 'en'
    stored = 'en'
    router = makeRouter()
    installPageHead(router, { locale, t }, () => stored)
  })

  afterEach(() => {
    document.head.innerHTML = ''
  })

  const description = () =>
    document.querySelector('meta[name="description"]')?.getAttribute('content')

  it('gives a public page its own title and description', async () => {
    await router.push('/terms')
    expect(document.title).toBe('en:preauth.seo.terms.title')
    expect(description()).toBe('en:preauth.seo.terms.description')
  })

  it('restores the defaults on an app page', async () => {
    await router.push('/terms')
    await router.push('/app/home')
    expect(document.title).toBe('Default title')
    expect(description()).toBe('Default description')
  })

  it('switches to the locale a prefixed URL pins', async () => {
    await router.push('/de/terms')
    expect(locale.value).toBe('de')
    expect(document.title).toBe('de:preauth.seo.terms.title')
  })

  it('returns to the stored choice when leaving a prefixed URL', async () => {
    stored = 'en'
    await router.push('/de')
    await router.push('/app/home')
    expect(locale.value).toBe('en')
  })

  it('leaves the locale alone on an unprefixed URL', async () => {
    locale.value = 'de'
    await router.push('/terms')
    expect(locale.value).toBe('de')
  })

  it('retitles the page when the locale changes in place', async () => {
    await router.push('/terms')
    locale.value = 'de'
    await nextTick()
    expect(document.title).toBe('de:preauth.seo.terms.title')
  })

  describe('a page that names its own title', () => {
    it('takes it from its title key', async () => {
      await router.push('/l/abc')
      expect(document.title).toBe('en:guestSignup.page.title')
      expect(description()).toBe('Default description')
    })

    it('keeps it through a change of locale', async () => {
      await router.push('/l/abc')
      locale.value = 'de'
      await nextTick()
      expect(document.title).toBe('de:guestSignup.page.title')
    })

    it('gives the default title back on the way out', async () => {
      await router.push('/l/abc')
      await router.push('/app/home')
      expect(document.title).toBe('Default title')
    })
  })

  describe('noindex', () => {
    const robots = () => document.head.querySelectorAll('meta[name="robots"]')

    it('asks search engines to stay off a guest page', async () => {
      await router.push('/l/abc')
      expect(robots()).toHaveLength(1)
      expect(robots()[0].getAttribute('content')).toBe(NOINDEX_CONTENT)
    })

    it('adds the tag once when going from one guest page to another', async () => {
      await router.push('/l/abc')
      await router.push('/guest-signup')
      expect(robots()).toHaveLength(1)
      expect(document.title).toBe('Default title')
    })

    it('takes it away again on an ordinary page', async () => {
      await router.push('/l/abc')
      await router.push('/terms')
      expect(robots()).toHaveLength(0)
    })

    it('corrects a robots tag that says something else', async () => {
      document.head.insertAdjacentHTML('beforeend', '<meta name="robots" content="index">')
      await router.push('/l/abc')
      expect(robots()).toHaveLength(1)
      expect(robots()[0].getAttribute('content')).toBe(NOINDEX_CONTENT)
    })
  })
})
