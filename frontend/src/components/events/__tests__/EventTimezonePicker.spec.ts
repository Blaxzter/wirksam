// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

import { afterEach, describe, expect, it, vi } from 'vitest'

import EventTimezonePicker from '@/components/events/EventTimezonePicker.vue'

import * as timezones from '@/lib/timezones'
import i18n from '@/locales/i18n'

/**
 * Which zones the picker lists and what picking one does. Reka's dialog is
 * stubbed down to its slots: portals and focus are reka's business.
 */
const slot = { template: '<div><slot /></div>' }

function mountPicker(modelValue = 'Europe/Berlin') {
  return mount(EventTimezonePicker, {
    props: {
      modelValue,
      'onUpdate:modelValue': (value: string) => wrapper.setProps({ modelValue: value }),
    },
    global: {
      plugins: [i18n],
      stubs: {
        DialogRoot: {
          props: ['open'],
          template: '<div v-if="open"><slot /></div>',
        },
        DialogPortal: slot,
        DialogOverlay: slot,
        DialogContent: slot,
        DialogTitle: slot,
        DialogDescription: slot,
        DialogClose: slot,
      },
    },
  })
}
let wrapper: ReturnType<typeof mountPicker>

async function openPicker(modelValue?: string) {
  wrapper = mountPicker(modelValue)
  await wrapper.get('[data-testid="timezone-picker"]').trigger('click')
  await nextTick()
}

const options = () =>
  wrapper.findAll('[data-testid^="timezone-option-"]').map((o) => o.text())

afterEach(() => {
  vi.restoreAllMocks()
})

describe('EventTimezonePicker', () => {
  it('shows the zone in the field, written for people', () => {
    wrapper = mountPicker('America/New_York')
    expect(wrapper.get('[data-testid="timezone-picker-value"]').text()).toBe('America/New York')
  })

  it('lists nothing until it is opened', () => {
    wrapper = mountPicker()
    expect(options()).toEqual([])
  })

  it('puts the current zone and the device’s own first', async () => {
    vi.spyOn(timezones, 'browserTimeZone').mockReturnValue('Asia/Tokyo')
    await openPicker('Europe/Lisbon')
    expect(options().slice(0, 2)).toEqual(['Europe/Lisbon', 'Asia/Tokyo'])
    expect(new Set(options()).size).toBe(options().length)
  })

  it('narrows the list down by what is typed', async () => {
    await openPicker()
    await wrapper.get('[data-testid="timezone-picker-input"]').setValue('new york')
    expect(options()).toEqual(['America/New York'])
  })

  it('says so when nothing matches', async () => {
    await openPicker()
    await wrapper.get('[data-testid="timezone-picker-input"]').setValue('olympus')
    expect(options()).toEqual([])
    expect(wrapper.text()).toContain(i18n.global.t('duties.events.timezone.noMatch'))
  })

  it('picks a zone and closes', async () => {
    await openPicker()
    await wrapper.get('[data-testid="timezone-option-Asia/Tokyo"]').trigger('click')
    await nextTick()
    expect(wrapper.emitted('update:modelValue')).toEqual([['Asia/Tokyo']])
    expect(wrapper.find('[data-testid="timezone-picker-input"]').exists()).toBe(false)
  })

  it('takes the first row on Enter, once something is typed', async () => {
    await openPicker()
    const input = wrapper.get('[data-testid="timezone-picker-input"]')
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    await input.setValue('tokyo')
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')).toEqual([['Asia/Tokyo']])
  })

  it('starts a new search each time it opens', async () => {
    await openPicker()
    await wrapper.get('[data-testid="timezone-picker-input"]').setValue('tokyo')
    await wrapper.get('[data-testid="timezone-option-Asia/Tokyo"]').trigger('click')
    await nextTick()
    await wrapper.get('[data-testid="timezone-picker"]').trigger('click')
    await nextTick()
    const input = wrapper.get('[data-testid="timezone-picker-input"]')
    expect((input.element as HTMLInputElement).value).toBe('')
  })
})
