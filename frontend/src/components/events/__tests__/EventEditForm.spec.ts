// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import EventEditForm from '@/components/events/EventEditForm.vue'

import type { EventRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * Status and visibility are what let a copied event, which starts as a draft,
 * go out at all: nothing else on screen sets them.
 */

const api = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), post: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => api,
}))
vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/lib/api-errors', () => ({ toastApiError: vi.fn() }))

const EVENT = {
  id: 'e1',
  name: 'Summer festival',
  description: null,
  start_date: '2027-07-01',
  end_date: '2027-07-03',
  timezone: 'Europe/Berlin',
  status: 'draft',
  visibility: 'private',
} as unknown as EventRead

const stub = { template: '<div />' }

async function mountForm(event: EventRead = EVENT) {
  api.get.mockResolvedValue({ data: { earliest_start: null, latest_end: null } })
  api.patch.mockResolvedValue({ data: event })
  const wrapper = mount(EventEditForm, {
    props: { event, eventId: event.id, tasks: [] },
    global: {
      plugins: [i18n],
      stubs: { DatePicker: stub, TimePicker: stub, EventTimezonePicker: stub },
    },
  })
  await flushPromises()
  return wrapper
}

const card = (w: Awaited<ReturnType<typeof mountForm>>, testid: string) =>
  w.get(`[data-testid="${testid}"]`)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('EventEditForm', () => {
  it('starts on the status and visibility the event has', async () => {
    const w = await mountForm()
    expect(card(w, 'btn-event-status-draft').attributes('aria-pressed')).toBe('true')
    expect(card(w, 'btn-visibility-private').attributes('aria-pressed')).toBe('true')
  })

  it('sends the chosen status and visibility when saving', async () => {
    const w = await mountForm()
    await card(w, 'btn-event-status-published').trigger('click')
    await card(w, 'btn-visibility-public').trigger('click')
    await w.get('form').trigger('submit')
    await flushPromises()

    expect(api.patch).toHaveBeenCalledOnce()
    expect(api.patch.mock.calls[0][0].body).toMatchObject({
      status: 'published',
      visibility: 'public',
    })
  })

  it('warns that a public event stays hidden until it is published', async () => {
    const w = await mountForm()
    expect(w.find('[data-testid="public-unpublished-note"]').exists()).toBe(false)

    await card(w, 'btn-visibility-public').trigger('click')
    expect(w.find('[data-testid="public-unpublished-note"]').exists()).toBe(true)

    await card(w, 'btn-event-status-published').trigger('click')
    expect(w.find('[data-testid="public-unpublished-note"]').exists()).toBe(false)
  })
})
