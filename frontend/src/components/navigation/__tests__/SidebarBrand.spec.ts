// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import SidebarBrand from '@/components/navigation/SidebarBrand.vue'

/**
 * The top of the sidebar: WirkSam's wordmark, or the open event's logo in its
 * place. A wide logo stands alone, a square one sits beside the event's name,
 * and the collapsed sidebar only has room for a square.
 */

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ name: 'home', path: '/', component: { template: '<div />' } }],
})

type Brand = InstanceType<typeof SidebarBrand>['$props']

function mountBrand(props: Brand) {
  return mount(SidebarBrand, { props, global: { plugins: [router] } })
}

const base = { id: 'e1', name: 'Riverside Festival', primary_color: 'violet' }
const wordmark = { ...base, logo_etag: 'v1', logo_width: 512, logo_height: 128 }
const mark = { ...base, logo_etag: 'v1', logo_width: 256, logo_height: 256 }
const logoSrc = `${import.meta.env.VITE_API_URL}/events/e1/logo?v=v1`

describe('SidebarBrand', () => {
  it('shows WirkSam without an event, or with one that has no logo', () => {
    for (const event of [null, base]) {
      const w = mountBrand({ collapsed: false, event })
      expect(w.find('[data-testid="sidebar-brand-app"]').exists()).toBe(true)
      expect(w.find('[data-testid="sidebar-brand-event"]').exists()).toBe(false)
      expect(w.get('img').attributes('alt')).toBe('WirkSam')
    }
  })

  it("shows WirkSam's mark when collapsed", () => {
    const w = mountBrand({ collapsed: true, event: null })
    expect(w.get('img').classes()).toContain('size-8')
    expect(w.get('a').attributes('aria-label')).toBeUndefined()
  })

  it('puts a wordmark in place of WirkSam, on its own', () => {
    const w = mountBrand({ collapsed: false, event: wordmark })
    const img = w.get('[data-testid="sidebar-brand-event"] img')
    expect(img.attributes('src')).toBe(logoSrc)
    expect(img.attributes('alt')).toBe('Riverside Festival')
    expect(img.attributes('width')).toBe('512')
    expect(w.text()).not.toContain('Riverside Festival')
    expect(w.find('[data-testid="sidebar-brand-app"]').exists()).toBe(false)
  })

  it('puts the wordmark straight on the sidebar, on white in dark mode only', () => {
    const tiled = mountBrand({ collapsed: false, event: wordmark }).get(
      '[data-testid="sidebar-brand-event"]',
    )
    expect(tiled.classes()).not.toContain('bg-white')
    expect(tiled.classes()).toContain('dark:bg-white')

    const bare = mountBrand({
      collapsed: false,
      event: { ...wordmark, logo_dark_etag: 'd1', logo_dark_tile: false },
    })
    expect(bare.get('[data-testid="sidebar-brand-event"]').classes()).not.toContain('dark:bg-white')
    expect(bare.get('[data-testid="event-logo-dark"]').attributes('alt')).toBe('Riverside Festival')
  })

  it('puts a square logo beside the event name', () => {
    const w = mountBrand({ collapsed: false, event: mark })
    const brand = w.get('[data-testid="sidebar-brand-event"]')
    expect(brand.get('[data-testid="event-logo"] img').attributes('src')).toBe(logoSrc)
    expect(brand.text()).toBe('Riverside Festival')
  })

  it('treats a logo of unknown size as a square one', () => {
    const w = mountBrand({ collapsed: false, event: { ...base, logo_etag: 'v1' } })
    expect(w.get('[data-testid="sidebar-brand-event"]').text()).toBe('Riverside Festival')
  })

  it('shows a square logo when collapsed, and the letter for a wordmark', () => {
    const square = mountBrand({ collapsed: true, event: mark })
    expect(square.get('[data-testid="event-logo"] img').attributes('src')).toBe(logoSrc)

    const wide = mountBrand({ collapsed: true, event: wordmark })
    expect(wide.find('[data-testid="event-logo"]').exists()).toBe(false)
    const letter = wide.get('[data-testid="event-logo-fallback"]')
    expect(letter.text()).toBe('R')
    expect(letter.attributes('data-event-primary')).toBe('violet')
    // The letter is hidden from screen readers, so the link carries the name.
    expect(wide.get('a').attributes('aria-label')).toBe('Riverside Festival')
  })

  it('links home', async () => {
    const w = mountBrand({ collapsed: false, event: wordmark })
    expect(w.get('a').attributes('href')).toBe('/')
  })
})
