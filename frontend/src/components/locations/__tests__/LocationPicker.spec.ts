// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Select } from '@/components/ui/select'

import LocationPicker from '@/components/locations/LocationPicker.vue'

import type { LocationRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * The picker's two models (`locationId`, `text`) and the three modes they map
 * to. The reka Select itself is driven through its `update:modelValue`.
 */

const stage: LocationRead = {
  id: 'loc-stage',
  event_id: 'e1',
  name: 'Main stage',
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-01T00:00:00Z',
}

const locations = ref<LocationRead[]>([stage])
vi.mock('@/composables/useLocations', () => ({
  useLocations: () => ({ locations, loading: ref(false), error: ref(null), reload: vi.fn() }),
  invalidateLocations: vi.fn(),
}))

const canManage = vi.fn(() => true)
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ canManageEvent: canManage }),
}))

beforeEach(() => {
  i18n.global.locale.value = 'en'
  locations.value = [stage]
  canManage.mockReturnValue(true)
})

function mountPicker(props: Record<string, unknown>) {
  return mount(LocationPicker, {
    props: { eventId: 'e1', ...props },
    global: {
      plugins: [i18n],
      stubs: { LocationFormDialog: { template: '<div data-stub="form" />', props: ['open'] } },
    },
  })
}

const selectValue = (w: ReturnType<typeof mountPicker>) =>
  w.findComponent(Select).props('modelValue')
const choose = async (w: ReturnType<typeof mountPicker>, value: string) => {
  w.findComponent(Select).vm.$emit('update:modelValue', value)
  await nextTick()
}

describe('LocationPicker', () => {
  it('starts on the linked location', () => {
    const w = mountPicker({ locationId: 'loc-stage', text: 'Main stage' })
    expect(selectValue(w)).toBe('loc-stage')
    expect(w.find('[data-testid="location-custom-input"]').exists()).toBe(false)
  })

  it('starts in free-text mode when there is only text', () => {
    const w = mountPicker({ locationId: null, text: 'Field gate' })
    expect(selectValue(w)).toBe('__custom')
    const input = w.find('[data-testid="location-custom-input"]')
    expect((input.element as HTMLInputElement).value).toBe('Field gate')
  })

  it('starts on "no location" when both are empty', () => {
    const w = mountPicker({ locationId: null, text: '' })
    expect(selectValue(w)).toBe('__none')
  })

  it('picking a location sets the id and the name as text', async () => {
    const w = mountPicker({ locationId: null, text: '' })
    await choose(w, 'loc-stage')
    expect(w.emitted('update:locationId')?.at(-1)).toEqual(['loc-stage'])
    expect(w.emitted('update:text')?.at(-1)).toEqual(['Main stage'])
  })

  it('"other" drops the link but keeps the text to edit', async () => {
    const w = mountPicker({ locationId: 'loc-stage', text: 'Main stage' })
    await choose(w, '__custom')
    expect(w.emitted('update:locationId')?.at(-1)).toEqual([null])
    expect(w.emitted('update:text')).toBeUndefined()
    expect(w.find('[data-testid="location-custom-input"]').exists()).toBe(true)
  })

  it('"no location" clears both', async () => {
    const w = mountPicker({ locationId: 'loc-stage', text: 'Main stage' })
    await choose(w, '__none')
    expect(w.emitted('update:locationId')?.at(-1)).toEqual([null])
    expect(w.emitted('update:text')?.at(-1)).toEqual([''])
  })

  it('"new location" opens the form and keeps the current choice', async () => {
    const w = mountPicker({ locationId: 'loc-stage', text: 'Main stage' })
    await choose(w, '__new')
    expect(selectValue(w)).toBe('loc-stage')
    expect(w.emitted('update:locationId')).toBeUndefined()
  })

  it('follows models that are filled in after mount', async () => {
    const w = mountPicker({ locationId: null, text: '' })
    await w.setProps({ locationId: 'loc-stage', text: 'Main stage' })
    expect(selectValue(w)).toBe('loc-stage')
  })

  it('stays in free-text mode while the text is cleared', async () => {
    const w = mountPicker({ locationId: null, text: 'Gate' })
    await w.setProps({ text: '' })
    expect(selectValue(w)).toBe('__custom')
  })

  it('hides "new location" without the right to manage the event', () => {
    canManage.mockReturnValue(false)
    const w = mountPicker({})
    expect(w.find('[data-stub="form"]').exists()).toBe(false)
  })

  it('never offers "new location" without an event', () => {
    const w = mountPicker({ eventId: null, allowCreate: true })
    expect(w.find('[data-stub="form"]').exists()).toBe(false)
  })

  it('asks for an event unless the caller hides the hint', () => {
    expect(
      mountPicker({ eventId: null }).find('[data-testid="location-picker-no-event"]').exists(),
    ).toBe(true)
    expect(
      mountPicker({ eventId: null, hideNoEventHint: true })
        .find('[data-testid="location-picker-no-event"]')
        .exists(),
    ).toBe(false)
  })
})
