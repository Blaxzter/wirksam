// @vitest-environment jsdom
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

import i18n from '@/locales/i18n'

/**
 * On a phone a Select opens as a dialog with a margin round it, not as a popup
 * beside the trigger (see `SelectContent.vue`). The trigger, the value and
 * `v-model` stay reka's; what is tested here is the phone half: the dialog,
 * its rows, the text the trigger shows while it is shut, and that the tap
 * which opened the dialog cannot pick a row by landing on it.
 */

const isPhone = ref(true)
vi.mock('@vueuse/core', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@vueuse/core')>()),
  useMediaQuery: () => isPhone,
}))

enableAutoUnmount(afterEach)
afterEach(() => {
  isPhone.value = true
})

function mountSelect(initial = 'b', label: Record<string, string> = { id: 'fruit' }) {
  const value = ref(initial)
  const wrapper = mount(
    defineComponent({
      setup: () => () =>
        h('div', [
          h('label', { for: 'fruit' }, 'Fruit'),
          h(
            Select,
            {
              modelValue: value.value,
              'onUpdate:modelValue': (v: unknown) => (value.value = String(v)),
            },
            () => [
              h(SelectTrigger, { 'data-testid': 'trigger', ...label }, () =>
                h(SelectValue, { placeholder: 'Pick one' }),
              ),
              h(SelectContent, null, () => [
                h(SelectItem, { value: 'a', 'data-testid': 'opt-a' }, () => 'Apple'),
                h(SelectItem, { value: 'b', 'data-testid': 'opt-b' }, () => 'Banana'),
                h(SelectItem, { value: 'c', disabled: true }, () => 'Cherry'),
              ]),
            ],
          ),
        ]),
    }),
    { attachTo: document.body, global: { plugins: [i18n] } },
  )
  return { wrapper, value }
}

async function open(wrapper: ReturnType<typeof mountSelect>['wrapper']) {
  // reka opens on pointerdown, which jsdom cannot replay faithfully; Enter
  // opens it the same way.
  await wrapper.get('[data-testid="trigger"]').trigger('keydown', { key: 'Enter' })
  await flushPromises()
  return document.querySelector<HTMLElement>('[role="dialog"]')
}

const row = (testid: string) =>
  document.querySelector<HTMLElement>(`[role="dialog"] [data-testid="${testid}"]`)!

function tap(el: HTMLElement) {
  el.dispatchEvent(new Event('pointerdown', { bubbles: true }))
  el.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 }))
}

describe('Select on a phone', () => {
  it('shows the chosen option on the trigger while the dialog is shut', async () => {
    const { wrapper } = mountSelect('b')
    await flushPromises()

    expect(wrapper.get('[data-testid="trigger"]').text()).toBe('Banana')
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    // The hidden copy carries no test ids, so tests and E2E find one row each.
    expect(document.querySelectorAll('[data-testid="opt-a"]')).toHaveLength(0)
  })

  it('opens a dialog titled with the trigger’s label, with the chosen row marked', async () => {
    const { wrapper } = mountSelect('b')
    const dialog = await open(wrapper)

    expect(dialog).not.toBeNull()
    expect(dialog!.querySelector('h2')!.textContent).toBe('Fruit')
    const options = [...dialog!.querySelectorAll('[role="option"]')]
    expect(options.map((o) => o.textContent!.trim())).toEqual(['Apple', 'Banana', 'Cherry'])
    expect(options.map((o) => o.getAttribute('aria-selected'))).toEqual(['false', 'true', 'false'])
    expect(document.activeElement).toBe(row('opt-b'))
  })

  it('falls back to the aria-label, then to a generic title', async () => {
    const named = mountSelect('b', { 'aria-label': 'Pick a fruit' })
    expect((await open(named.wrapper))!.querySelector('h2')!.textContent).toBe('Pick a fruit')
    named.wrapper.unmount()

    const bare = mountSelect('b', {})
    expect((await open(bare.wrapper))!.querySelector('h2')!.textContent).toBe('Choose one')
  })

  it('picks a tapped row, closes and puts focus back on the trigger', async () => {
    const { wrapper, value } = mountSelect('b')
    await open(wrapper)

    tap(row('opt-a'))
    await flushPromises()

    expect(value.value).toBe('a')
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(wrapper.get('[data-testid="trigger"]').text()).toBe('Apple')
    expect(document.activeElement).toBe(wrapper.get('[data-testid="trigger"]').element)
  })

  it('ignores the opening tap’s click when it lands on a row', async () => {
    const { wrapper, value } = mountSelect('b')
    await open(wrapper)

    // No press on the row first: this is the click the browser sends after
    // the tap that opened the dialog, to whatever is under the finger by then.
    row('opt-a').dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 }))
    await flushPromises()

    expect(value.value).toBe('b')
    expect(document.querySelector('[role="dialog"]')).not.toBeNull()
  })

  it('picks with the keyboard, which clicks without a press', async () => {
    const { wrapper, value } = mountSelect('b')
    await open(wrapper)

    row('opt-a').dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 0 }))
    await flushPromises()

    expect(value.value).toBe('a')
  })

  it('does not pick a disabled row', async () => {
    const { wrapper, value } = mountSelect('b')
    const dialog = await open(wrapper)
    const cherry = [...dialog!.querySelectorAll<HTMLButtonElement>('[role="option"]')][2]!

    expect(cherry.disabled).toBe(true)
    tap(cherry)
    await flushPromises()
    expect(value.value).toBe('b')
  })

  it('keeps the popup beside the trigger on a larger screen', async () => {
    isPhone.value = false
    const { wrapper } = mountSelect('b')
    await flushPromises()

    expect(wrapper.get('[data-testid="trigger"]').text()).toBe('Banana')
    expect(document.querySelector('[data-slot="select-phone-options"]')).toBeNull()
    await open(wrapper)
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(document.querySelector('[role="listbox"]')).not.toBeNull()
  })
})
