// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { describe, expect, it } from 'vitest'

import EventLogo from '@/components/events/EventLogo.vue'

const base = { id: 'e1', name: 'summer fair' }

describe('EventLogo', () => {
  it('shows the logo at its versioned URL', () => {
    const w = mount(EventLogo, { props: { event: { ...base, logo_etag: 'v1' } } })
    const img = w.get('[data-testid="event-logo"] img')
    expect(img.attributes('src')).toBe(`${import.meta.env.VITE_API_URL}/events/e1/logo?v=v1`)
    expect(img.attributes('alt')).toBe('')
  })

  it('sits straight on the page, and on a white tile in dark mode only', () => {
    const tile = mount(EventLogo, { props: { event: { ...base, logo_etag: 'v1' } } }).get(
      '[data-testid="event-logo"]',
    )
    expect(tile.classes()).not.toContain('bg-white')
    expect(tile.classes()).not.toContain('border')
    expect(tile.classes()).toEqual(expect.arrayContaining(['dark:bg-white', 'dark:border']))
  })

  it('leaves out the tile when the organisers switched it off', () => {
    const tile = mount(EventLogo, {
      props: { event: { ...base, logo_etag: 'v1', logo_dark_tile: false } },
    }).get('[data-testid="event-logo"]')
    expect(tile.classes()).not.toContain('dark:bg-white')
  })

  it('swaps in the version for dark mode where there is one', () => {
    const w = mount(EventLogo, {
      props: { event: { ...base, logo_etag: 'v1', logo_dark_etag: 'd1' } },
    })
    const light = w.get('[data-testid="event-logo-light"]')
    const dark = w.get('[data-testid="event-logo-dark"]')
    expect(light.classes()).toContain('dark:hidden')
    expect(dark.attributes('src')).toBe(`${import.meta.env.VITE_API_URL}/events/e1/logo/dark?v=d1`)
    expect(dark.classes()).toEqual(expect.arrayContaining(['hidden', 'dark:block']))

    // Without one, the logo shows in both modes.
    const plain = mount(EventLogo, { props: { event: { ...base, logo_etag: 'v1' } } })
    expect(plain.find('[data-testid="event-logo-dark"]').exists()).toBe(false)
    expect(plain.get('[data-testid="event-logo-light"]').classes()).not.toContain('dark:hidden')
  })

  it('falls back to the letter when the version for dark mode fails too', async () => {
    const w = mount(EventLogo, {
      props: { event: { ...base, logo_etag: 'v1', logo_dark_etag: 'd1' } },
    })
    await w.get('[data-testid="event-logo-dark"]').trigger('error')
    expect(w.get('[data-testid="event-logo-fallback"]').text()).toBe('S')
  })

  it('takes alt text when it stands for the event on its own', () => {
    const w = mount(EventLogo, {
      props: { event: { ...base, logo_etag: 'v1' }, alt: 'Summer fair' },
    })
    expect(w.get('img').attributes('alt')).toBe('Summer fair')
  })

  it('shows the first letter on the event colour without a logo', () => {
    const w = mount(EventLogo, { props: { event: { ...base, primary_color: 'teal' } } })
    const tile = w.get('[data-testid="event-logo-fallback"]')
    expect(tile.text()).toBe('S')
    expect(tile.attributes('data-event-primary')).toBe('teal')
    expect(tile.attributes('aria-hidden')).toBe('true')
    expect(tile.classes()).toContain('bg-(--event-primary)')
  })

  it('shows the letter on an own main colour', () => {
    const tile = mount(EventLogo, {
      props: { event: { ...base, primary_color: '#1E6BB8' } },
    }).get('[data-testid="event-logo-fallback"]')
    expect(tile.attributes('data-event-primary')).toBe('#1e6bb8')
    expect(tile.classes()).toContain('bg-(--event-primary)')
  })

  it('stays neutral without a colour, and ignores one it does not know', () => {
    for (const primary_color of [null, 'chartreuse']) {
      const tile = mount(EventLogo, { props: { event: { ...base, primary_color } } }).get(
        '[data-testid="event-logo-fallback"]',
      )
      expect(tile.attributes('data-event-primary')).toBeUndefined()
      expect(tile.classes()).toContain('bg-muted')
    }
  })

  it('renders nothing without a logo when asked not to fall back', () => {
    const w = mount(EventLogo, { props: { event: base, fallback: false } })
    expect(w.html()).toBe('<!--v-if-->')
  })

  it('falls back to the letter when the image fails, until there is a new one', async () => {
    const w = mount(EventLogo, { props: { event: { ...base, logo_etag: 'v1' } } })
    await w.get('img').trigger('error')
    expect(w.find('[data-testid="event-logo"]').exists()).toBe(false)
    expect(w.get('[data-testid="event-logo-fallback"]').text()).toBe('S')

    await w.setProps({ event: { ...base, logo_etag: 'v2' } })
    expect(w.get('[data-testid="event-logo"] img').attributes('src')).toContain('v=v2')
  })

  it('takes its size and extra classes', () => {
    const w = mount(EventLogo, { props: { event: base, size: 'xl', class: 'mx-auto' } })
    const classes = w.get('[data-testid="event-logo-fallback"]').classes()
    expect(classes).toContain('h-16')
    expect(classes).toContain('aspect-square')
    expect(classes).toContain('mx-auto')
  })

  describe('a wordmark', () => {
    const wordmark = { ...base, logo_etag: 'v1', logo_width: 512, logo_height: 128 }

    it("gets a tile in the logo's proportions, up to a cap", () => {
      const tile = mount(EventLogo, { props: { event: wordmark, size: 'lg' } }).get(
        '[data-testid="event-logo"]',
      )
      expect(tile.attributes('style')).toContain('aspect-ratio: 512 / 128')
      expect(tile.classes()).toContain('h-12')
      expect(tile.classes()).toContain('max-w-48')
      expect(tile.classes()).not.toContain('aspect-square')
    })

    it('gives way to the letter where it would be too small to read', () => {
      for (const size of ['xs', 'sm'] as const) {
        const w = mount(EventLogo, { props: { event: wordmark, size } })
        expect(w.find('[data-testid="event-logo"]').exists()).toBe(false)
        expect(w.get('[data-testid="event-logo-fallback"]').text()).toBe('S')
      }
      const none = mount(EventLogo, { props: { event: wordmark, size: 'xs', fallback: false } })
      expect(none.html()).toBe('<!--v-if-->')
    })

    it('keeps a square logo square', () => {
      const square = { ...base, logo_etag: 'v1', logo_width: 300, logo_height: 200 }
      const tile = mount(EventLogo, { props: { event: square, size: 'sm' } }).get(
        '[data-testid="event-logo"]',
      )
      expect(tile.classes()).toContain('aspect-square')
      expect(tile.attributes('style')).toBeUndefined()
    })
  })
})
