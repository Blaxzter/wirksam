// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import EventAppearanceSettings from '@/components/events/EventAppearanceSettings.vue'

import type { EventRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * The organisers' "Colour and logo" card: a colour, a base tone or the dark
 * mode tile saves on the click, a logo on the file pick, and all hand the
 * updated event back and refresh the open one so the page changes at once.
 */

const api = vi.hoisted(() => ({
  getAuthToken: vi.fn(() => Promise.resolve('tok')),
  patch: vi.fn(),
  delete: vi.fn(),
}))
vi.mock('@/composables/useAuthenticatedClient', () => ({ useAuthenticatedClient: () => api }))
const store = vi.hoisted(() => ({
  profile: { is_sandbox: false } as { is_sandbox: boolean },
  refreshSelectedEvent: vi.fn(() => Promise.resolve()),
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => store }))
const errors = vi.hoisted(() => ({ toastApiError: vi.fn() }))
vi.mock('@/lib/api-errors', () => errors)
vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

function event(overrides: Partial<EventRead> = {}): EventRead {
  return {
    id: 'e1',
    name: 'Summer fair',
    start_date: '2026-07-17',
    end_date: '2026-07-19',
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
    timezone: 'Europe/Berlin',
    primary_color: null,
    secondary_color: null,
    logo_etag: null,
    can_manage: true,
    is_expired: false,
    ...overrides,
  } as EventRead
}

function mountCard(e: EventRead = event()) {
  return mount(EventAppearanceSettings, {
    props: { event: e },
    global: { plugins: [i18n] },
    attachTo: document.body,
  })
}

const fetchMock = vi.fn()

beforeEach(() => {
  i18n.global.locale.value = 'en'
  api.patch.mockReset()
  api.delete.mockReset()
  store.profile = { is_sandbox: false }
  store.refreshSelectedEvent.mockClear()
  errors.toastApiError.mockClear()
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('EventAppearanceSettings: colours', () => {
  it('offers the default and every preset for each colour, with the current ones checked', () => {
    const w = mountCard(event({ primary_color: 'blue', secondary_color: 'yellow' }))
    const radios = (kind: string) =>
      w.findAll(`[data-testid="event-colour-${kind}"] [role="radio"]`)
    expect(radios('primary')).toHaveLength(9)
    // Yellow and green only as the second colour.
    expect(radios('secondary')).toHaveLength(11)
    expect(w.find('[data-testid="event-primary-yellow"]').exists()).toBe(false)

    expect(w.get('[data-testid="event-primary-blue"]').attributes('aria-checked')).toBe('true')
    expect(w.get('[data-testid="event-primary-none"]').attributes('aria-checked')).toBe('false')
    expect(w.get('[data-testid="event-secondary-yellow"]').attributes('aria-checked')).toBe('true')
    expect(w.get('[data-testid="event-primary-teal"]').text()).toBe('Teal')
    expect(w.get('[data-testid="event-secondary-green"]').text()).toBe('Green')
  })

  it('names each picker for a screen reader', () => {
    const w = mountCard()
    const group = w.get('[data-testid="event-colour-secondary"] [role="radiogroup"]')
    const label = w.get(`#${group.attributes('aria-labelledby')}`)
    expect(label.text()).toBe('Second colour')
  })

  it('saves a picked main colour and hands the event back', async () => {
    const updated = event({ primary_color: 'teal' })
    api.patch.mockResolvedValue({ data: updated })
    const w = mountCard()
    await w.get('[data-testid="event-primary-teal"]').trigger('click')
    await flushPromises()

    expect(api.patch).toHaveBeenCalledWith({ url: '/events/e1', body: { primary_color: 'teal' } })
    expect(w.emitted('updated')?.[0]).toEqual([updated])
    expect(store.refreshSelectedEvent).toHaveBeenCalledWith('e1')
  })

  it('saves a picked second colour on its own', async () => {
    api.patch.mockResolvedValue({ data: event({ secondary_color: 'green' }) })
    const w = mountCard(event({ primary_color: 'red' }))
    await w.get('[data-testid="event-secondary-green"]').trigger('click')
    await flushPromises()
    expect(api.patch).toHaveBeenCalledWith({
      url: '/events/e1',
      body: { secondary_color: 'green' },
    })
  })

  it('sends null to go back to the app colours', async () => {
    api.patch.mockResolvedValue({ data: event() })
    const w = mountCard(event({ primary_color: 'red', secondary_color: 'blue' }))
    await w.get('[data-testid="event-secondary-none"]').trigger('click')
    await flushPromises()
    expect(api.patch).toHaveBeenCalledWith({ url: '/events/e1', body: { secondary_color: null } })
  })

  it('does not save the colour it already has', async () => {
    const w = mountCard(event({ primary_color: 'red', secondary_color: 'red' }))
    await w.get('[data-testid="event-primary-red"]').trigger('click')
    await w.get('[data-testid="event-secondary-red"]').trigger('click')
    await flushPromises()
    expect(api.patch).not.toHaveBeenCalled()
  })

  it('reports a failed save', async () => {
    api.patch.mockRejectedValue(new Error('nope'))
    const w = mountCard()
    await w.get('[data-testid="event-primary-pink"]').trigger('click')
    await flushPromises()
    expect(errors.toastApiError).toHaveBeenCalled()
    expect(w.emitted('updated')).toBeUndefined()
  })
})

describe('EventAppearanceSettings: an own colour', () => {
  it('saves a picked own colour like a preset', async () => {
    api.patch.mockResolvedValue({ data: event({ primary_color: '#1e6bb8' }) })
    const w = mountCard()
    await w.get('[data-testid="event-primary-own"]').trigger('click')
    const field = w.get('[data-testid="event-primary-own-input"]')
    ;(field.element as HTMLInputElement).value = '#1e6bb8'
    await field.trigger('change')
    await flushPromises()
    expect(api.patch).toHaveBeenCalledWith({
      url: '/events/e1',
      body: { primary_color: '#1e6bb8' },
    })
  })

  it('shows the saved one, with what it became', () => {
    const w = mountCard(event({ secondary_color: '#1e3a8a' }))
    expect(w.get('[data-testid="event-secondary-own"]').attributes('aria-checked')).toBe('true')
    expect(w.get('[data-testid="event-secondary-own-light"]').attributes('data-adjusted')).toBe(
      'true',
    )
  })
})

describe('EventAppearanceSettings: base tone', () => {
  it('offers the default, the main colour and every tone, with the current one checked', () => {
    const w = mountCard(event({ base_color: 'rose' }))
    const radios = w.findAll('[data-testid="event-colour-base"] [role="radio"]')
    expect(radios).toHaveLength(9)
    expect(w.get('[data-testid="event-base-rose"]').attributes('aria-checked')).toBe('true')
    expect(w.get('[data-testid="event-base-rose"]').text()).toBe('Rose')
    expect(w.get('[data-testid="event-base-primary"]').text()).toBe('Like main colour')
    expect(w.get('[data-testid="event-base-neutral"]').text()).toBe('Neutral')
  })

  it('shows the main colour on the swatch that follows it', () => {
    const swatch = (e: EventRead) =>
      mountCard(e).get('[data-testid="event-base-primary"] [data-event-base]')
    expect(swatch(event({ primary_color: 'violet' })).attributes('data-event-primary')).toBe(
      'violet',
    )
    expect(swatch(event()).attributes('data-event-primary')).toBeUndefined()
    // The others are their own tone.
    const blue = mountCard().get('[data-testid="event-base-blue"] [data-event-base]')
    expect(blue.attributes('data-event-base')).toBe('blue')
    expect(blue.attributes('data-event-primary')).toBeUndefined()
  })

  it('saves a picked tone, and null to go back to the cream', async () => {
    api.patch.mockResolvedValue({ data: event({ base_color: 'teal' }) })
    const w = mountCard()
    await w.get('[data-testid="event-base-teal"]').trigger('click')
    await flushPromises()
    expect(api.patch).toHaveBeenCalledWith({ url: '/events/e1', body: { base_color: 'teal' } })

    api.patch.mockClear()
    const toned = mountCard(event({ base_color: 'teal' }))
    await toned.get('[data-testid="event-base-none"]').trigger('click')
    await flushPromises()
    expect(api.patch).toHaveBeenCalledWith({ url: '/events/e1', body: { base_color: null } })
  })
})

describe('EventAppearanceSettings: logo', () => {
  async function pickFile(w: ReturnType<typeof mountCard>) {
    const input = w.get('[data-testid="event-logo-input"]')
    const file = new File(['png'], 'logo.png', { type: 'image/png' })
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await flushPromises()
  }

  it('uploads a picked file and hands the event back', async () => {
    const updated = event({ logo_etag: 'v1' })
    fetchMock.mockResolvedValue(new Response(JSON.stringify(updated), { status: 200 }))
    const w = mountCard()
    expect(w.get('[data-testid="btn-event-logo-upload"]').text()).toBe('Upload logo')
    await pickFile(w)

    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe(`${import.meta.env.VITE_API_URL}/events/e1/logo`)
    expect(init.method).toBe('PUT')
    expect(init.headers).toEqual({ Authorization: 'Bearer tok' })
    expect((init.body as FormData).get('file')).toBeInstanceOf(File)
    expect(w.emitted('updated')?.[0]).toEqual([updated])
    expect(store.refreshSelectedEvent).toHaveBeenCalledWith('e1')
  })

  it('passes the server problem on when the upload is refused', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ code: 'event.invalid_logo' }), { status: 400 }),
    )
    const w = mountCard()
    await pickFile(w)
    const error = errors.toastApiError.mock.calls[0]![0] as {
      response: { status: number; data: unknown }
    }
    expect(error.response).toEqual({ status: 400, data: { code: 'event.invalid_logo' } })
    expect(w.emitted('updated')).toBeUndefined()
  })

  it('ignores a change with no file', async () => {
    const w = mountCard()
    const input = w.get('[data-testid="event-logo-input"]')
    Object.defineProperty(input.element, 'files', { value: [], configurable: true })
    await input.trigger('change')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('offers to replace and remove an existing logo', async () => {
    api.delete.mockResolvedValue({ data: event() })
    const w = mountCard(event({ logo_etag: 'v1' }))
    expect(w.get('[data-testid="btn-event-logo-upload"]').text()).toBe('Replace logo')
    await w.get('[data-testid="btn-event-logo-remove"]').trigger('click')
    await flushPromises()
    expect(api.delete).toHaveBeenCalledWith({ url: '/events/e1/logo' })
    expect(w.emitted('updated')?.[0]).toEqual([event()])
  })

  it('reports a failed removal', async () => {
    api.delete.mockRejectedValue(new Error('nope'))
    const w = mountCard(event({ logo_etag: 'v1' }))
    await w.get('[data-testid="btn-event-logo-remove"]').trigger('click')
    await flushPromises()
    expect(errors.toastApiError).toHaveBeenCalled()
  })

  it('has no remove button without a logo', () => {
    expect(mountCard().find('[data-testid="btn-event-logo-remove"]').exists()).toBe(false)
  })

  it('says a logo is best on a see-through background', () => {
    expect(mountCard().text()).toContain('best on a see-through background')
  })

  it('cannot upload in a demo, and says so', () => {
    for (const w of [
      mountCard(event({ is_sandbox: true })),
      (() => {
        store.profile = { is_sandbox: true }
        return mountCard()
      })(),
    ]) {
      expect(w.get('[data-testid="btn-event-logo-upload"]').attributes('disabled')).toBeDefined()
      expect(w.text()).toContain('Logos cannot be uploaded in a demo.')
    }
  })
})

describe('EventAppearanceSettings: dark mode', () => {
  const withLogo = (overrides: Partial<EventRead> = {}) => event({ logo_etag: 'v1', ...overrides })

  async function pickDarkFile(w: ReturnType<typeof mountCard>) {
    const input = w.get('[data-testid="event-logo-dark-input"]')
    const file = new File(['png'], 'logo-dark.png', { type: 'image/png' })
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await flushPromises()
  }

  it('only appears once there is a logo', () => {
    expect(mountCard().find('[data-testid="event-logo-dark-section"]').exists()).toBe(false)
    expect(mountCard(withLogo()).find('[data-testid="event-logo-dark-section"]').exists()).toBe(
      true,
    )
  })

  it('previews the logo as dark mode shows it', () => {
    const preview = mountCard(withLogo({ logo_dark_etag: 'd1' })).get(
      '[data-testid="event-logo-dark-preview"]',
    )
    // `dark` on the box turns on the `dark:` styles inside it.
    expect(preview.classes()).toContain('dark')
    expect(preview.get('[data-testid="event-logo-dark"]').attributes('src')).toContain(
      '/logo/dark?v=d1',
    )
  })

  it('uploads a version for dark mode to its own address', async () => {
    const updated = withLogo({ logo_dark_etag: 'd1' })
    fetchMock.mockResolvedValue(new Response(JSON.stringify(updated), { status: 200 }))
    const w = mountCard(withLogo())
    expect(w.get('[data-testid="btn-event-logo-dark-upload"]').text()).toBe('Upload dark version')
    await pickDarkFile(w)

    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe(`${import.meta.env.VITE_API_URL}/events/e1/logo/dark`)
    expect(init.method).toBe('PUT')
    expect(w.emitted('updated')?.[0]).toEqual([updated])
  })

  it('replaces and removes the version for dark mode on its own', async () => {
    api.delete.mockResolvedValue({ data: withLogo() })
    const w = mountCard(withLogo({ logo_dark_etag: 'd1' }))
    expect(w.get('[data-testid="btn-event-logo-dark-upload"]').text()).toBe('Replace dark version')
    await w.get('[data-testid="btn-event-logo-dark-remove"]').trigger('click')
    await flushPromises()
    expect(api.delete).toHaveBeenCalledWith({ url: '/events/e1/logo/dark' })
    expect(w.emitted('updated')?.[0]).toEqual([withLogo()])
  })

  it('switches the white background off and on', async () => {
    api.patch.mockResolvedValue({ data: withLogo({ logo_dark_tile: false }) })
    const w = mountCard(withLogo())
    const toggle = w.get('[data-testid="switch-event-logo-dark-tile"]')
    expect(toggle.attributes('aria-checked')).toBe('true')
    await toggle.trigger('click')
    await flushPromises()
    expect(api.patch).toHaveBeenCalledWith({ url: '/events/e1', body: { logo_dark_tile: false } })
    expect(w.emitted('updated')?.[0]).toEqual([withLogo({ logo_dark_tile: false })])

    const off = mountCard(withLogo({ logo_dark_tile: false }))
    expect(off.get('[data-testid="switch-event-logo-dark-tile"]').attributes('aria-checked')).toBe(
      'false',
    )
  })

  it('reports a failed switch', async () => {
    api.patch.mockRejectedValue(new Error('nope'))
    const w = mountCard(withLogo())
    await w.get('[data-testid="switch-event-logo-dark-tile"]').trigger('click')
    await flushPromises()
    expect(errors.toastApiError).toHaveBeenCalled()
  })
})
