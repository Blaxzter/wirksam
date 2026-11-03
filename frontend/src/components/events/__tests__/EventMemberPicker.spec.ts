// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import EventMemberPicker from '@/components/events/EventMemberPicker.vue'

import type { EventMemberRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * Typing an address into the people-in-charge picker: an address no member
 * has is offered as "Invite …", a member's address finds the member, and
 * pickers that did not ask for it (teams, corrections, redeem) never offer to
 * invite anyone. On a phone the same choices sit in a full-screen sheet.
 *
 * The combobox is stubbed down to its slots: reka renders its list in a
 * portal and only while open, which is reka's business, not this
 * component's. What is tested is which rows it is given and what picking one
 * emits.
 */

const isPhone = ref(false)
vi.mock('@vueuse/core', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@vueuse/core')>()),
  useMediaQuery: () => isPhone,
}))

function member(id: string, name: string, email: string): EventMemberRead {
  return {
    user_id: id,
    event_id: 'e1',
    role: 'member',
    name,
    email,
    joined_at: '2026-10-01T00:00:00',
  } as EventMemberRead
}

const members = [
  member('u-jonas', 'Jonas Albrecht', 'jonas.albrecht@example.org'),
  member('u-mira', 'Mira Lindqvist', 'mira.l@example.org'),
  member('u-pia', 'Pia Incharge', 'pia@example.org'),
]

const slot = { template: '<div><slot /></div>' }
const comboboxStubs = {
  Combobox: {
    name: 'Combobox',
    emits: ['update:modelValue', 'update:open'],
    template: '<div><slot /></div>',
  },
  ComboboxAnchor: slot,
  ComboboxList: slot,
  ComboboxViewport: slot,
  ComboboxEmpty: { template: '<div data-stub="empty"><slot /></div>' },
  ComboboxInput: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template:
      '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  ComboboxItem: {
    props: ['value', 'textValue', 'disabled'],
    template: '<div role="option" :data-value="value"><slot /></div>',
  },
}

function mountPicker(props: Record<string, unknown> = {}) {
  return mount(EventMemberPicker, {
    props: { members, label: 'Add a person', testid: 'p', ...props },
    attachTo: document.body,
    global: { plugins: [i18n], stubs: comboboxStubs },
  })
}

type Wrapper = ReturnType<typeof mountPicker>

async function type(w: Wrapper, text: string) {
  await w.find('input[data-testid="p"]').setValue(text)
}

/** What reka reports when a row is picked. */
function pickValue(w: Wrapper, value: string) {
  w.findComponent({ name: 'Combobox' }).vm.$emit('update:modelValue', value)
}

const options = (w: Wrapper) => w.findAll('[role="option"]').map((o) => o.attributes('data-value'))

let wrapper: Wrapper | null = null

beforeEach(() => {
  i18n.global.locale.value = 'en'
  isPhone.value = false
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  document.body.innerHTML = ''
})

describe('EventMemberPicker with allowEmail', () => {
  it('offers to invite an address no member has, first, and emits it', async () => {
    wrapper = mountPicker({ allowEmail: true })
    await type(wrapper, '  New.Person@Example.org ')

    expect(options(wrapper)[0]).toBe('invite:New.Person@Example.org')
    expect(wrapper.find('[data-testid="p-invite"]').text()).toContain(
      'Invite New.Person@Example.org',
    )

    // Reka clears the search before it reports the pick, so the address has
    // to come with the picked value.
    await type(wrapper, '')
    pickValue(wrapper, 'invite:New.Person@Example.org')
    await nextTick()

    expect(wrapper.emitted('invite')).toEqual([['New.Person@Example.org']])
    expect(wrapper.emitted('pick')).toBeUndefined()
    // The field clears for the next name.
    expect((wrapper.find('input[data-testid="p"]').element as HTMLInputElement).value).toBe('')
  })

  it('finds the member behind a member’s address instead of offering an invitation', async () => {
    wrapper = mountPicker({ allowEmail: true })
    await type(wrapper, 'MIRA.L@example.org')

    expect(wrapper.find('[data-testid="p-invite"]').exists()).toBe(false)
    expect(options(wrapper)).toEqual(['u-mira'])

    pickValue(wrapper, 'u-mira')
    await nextTick()
    expect(wrapper.emitted('pick')?.[0]?.[0]).toMatchObject({ user_id: 'u-mira' })
  })

  it('lists members whose name looks like the address under the invitation', async () => {
    wrapper = mountPicker({ allowEmail: true })
    await type(wrapper, 'jonas.weber@example.org')

    expect(options(wrapper)).toEqual(['invite:jonas.weber@example.org', 'u-jonas'])
    expect(wrapper.find('[data-testid="p-option-u-jonas"]').text()).toContain('in the event')
  })

  it('does not offer half-typed addresses', async () => {
    wrapper = mountPicker({ allowEmail: true })
    await type(wrapper, 'jonas.weber@example')
    expect(wrapper.find('[data-testid="p-invite"]').exists()).toBe(false)
  })

  it('never offers to invite without allowEmail', async () => {
    wrapper = mountPicker()
    await type(wrapper, 'new.person@example.org')

    expect(wrapper.find('[data-testid="p-invite"]').exists()).toBe(false)
    expect(options(wrapper)).toEqual([])
    pickValue(wrapper, 'invite:new.person@example.org')
    await nextTick()
    expect(wrapper.emitted('invite')).toBeUndefined()
  })

  it('renders nothing with hideField on a wider screen', () => {
    wrapper = mountPicker({ phoneSheet: true, hideField: true })
    expect(wrapper.find('input').exists()).toBe(false)
    expect(wrapper.find('label').exists()).toBe(false)
    expect(options(wrapper)).toEqual([])
  })

  it('puts the trailing slot into each dropdown row', () => {
    wrapper = mount(EventMemberPicker, {
      props: { members, label: 'Pick', testid: 'p' },
      attachTo: document.body,
      global: { plugins: [i18n], stubs: comboboxStubs },
      slots: {
        trailing:
          '<template #trailing="{ member }"><b class="n">{{ member.user_id }}</b></template>',
      },
    })
    expect(wrapper.find('[data-testid="p-option-u-mira"] .n').text()).toBe('u-mira')
  })

  it('does not pick someone who is unavailable', async () => {
    wrapper = mountPicker({ unavailable: { 'u-pia': 'Already in charge' } })
    pickValue(wrapper, 'u-pia')
    await nextTick()
    expect(wrapper.emitted('pick')).toBeUndefined()
    // Pickable people come first.
    expect(options(wrapper).at(-1)).toBe('u-pia')
  })
})

describe('EventMemberPicker on a phone with phoneSheet', () => {
  const sheet = () => document.querySelector('[data-testid="p-sheet"]')
  const sheetInput = () =>
    document.querySelector<HTMLInputElement>('[data-testid="p-sheet-input"]')!

  async function typeInSheet(text: string) {
    sheetInput().value = text
    sheetInput().dispatchEvent(new Event('input'))
    await nextTick()
  }

  it('opens a full-screen sheet from the field and invites from its card', async () => {
    isPhone.value = true
    wrapper = mountPicker({
      allowEmail: true,
      phoneSheet: true,
      sheetContext: 'In charge of Bar. Not in the event? Enter their e-mail address.',
    })
    expect(sheet()).toBeNull()

    await wrapper.find('button[data-testid="p"]').trigger('click')
    await nextTick()
    expect(sheet()).not.toBeNull()
    expect(sheet()!.textContent).toContain('In charge of Bar.')
    expect(sheet()!.textContent).toContain('All members')

    await typeInSheet('new.person@example.org')
    const card = document.querySelector<HTMLButtonElement>('[data-testid="p-invite"]')!
    expect(card.textContent).toContain('Invite by e-mail')
    card.click()
    await nextTick()

    expect(wrapper.emitted('invite')).toEqual([['new.person@example.org']])
  })

  it('picks a member from the list, and Enter takes the first one that can be picked', async () => {
    isPhone.value = true
    wrapper = mountPicker({
      phoneSheet: true,
      unavailable: { 'u-mira': 'Already in charge' },
    })
    await wrapper.find('button[data-testid="p"]').trigger('click')
    await nextTick()

    const mira = document.querySelector<HTMLButtonElement>('[data-testid="p-option-u-mira"]')!
    expect(mira.disabled).toBe(true)
    expect(mira.textContent).toContain('Already in charge')

    await typeInSheet('a')
    sheetInput().dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))
    await nextTick()
    expect(wrapper.emitted('pick')?.[0]?.[0]).toMatchObject({ user_id: 'u-jonas' })
  })

  it('does nothing on Enter before anything is typed', async () => {
    isPhone.value = true
    wrapper = mountPicker({ allowEmail: true, phoneSheet: true })
    await wrapper.find('button[data-testid="p"]').trigger('click')
    await nextTick()

    // Nothing is highlighted in the sheet, so "Go" must not put the first
    // member of the roster in charge.
    await typeInSheet('   ')
    sheetInput().dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))
    await nextTick()
    expect(wrapper.emitted('pick')).toBeUndefined()
    expect(wrapper.emitted('invite')).toBeUndefined()
    expect(sheet()).not.toBeNull()
  })

  it('leaves the field out with hideField: the parent opens the sheet itself', async () => {
    isPhone.value = true
    wrapper = mountPicker({ phoneSheet: true, hideField: true, sheetOpen: false })
    expect(wrapper.find('[data-testid="p"]').exists()).toBe(false)
    expect(wrapper.find('label').exists()).toBe(false)
    expect(sheet()).toBeNull()

    await wrapper.setProps({ sheetOpen: true })
    await nextTick()
    expect(sheet()).not.toBeNull()

    document.querySelector<HTMLButtonElement>('[data-testid="p-option-u-jonas"]')!.click()
    await nextTick()
    expect(wrapper.emitted('pick')?.[0]?.[0]).toMatchObject({ user_id: 'u-jonas' })
    // Picking closes the sheet the parent opened.
    expect(wrapper.emitted('update:sheetOpen')?.at(-1)).toEqual([false])
  })

  it('shows what the parent puts at the end of each row', async () => {
    isPhone.value = true
    wrapper = mount(EventMemberPicker, {
      props: { members, label: 'Pick', testid: 'p', phoneSheet: true, hideField: true },
      attachTo: document.body,
      global: { plugins: [i18n], stubs: comboboxStubs },
      slots: {
        trailing:
          '<template #trailing="{ member }"><b class="n">{{ member.name.length }}</b></template>',
      },
    })
    await wrapper.setProps({ sheetOpen: true })
    await nextTick()
    const jonas = document.querySelector('[data-testid="p-option-u-jonas"]')!
    expect(jonas.querySelector('.n')?.textContent).toBe(String('Jonas Albrecht'.length))
  })

  it('keeps the dropdown on a phone when the caller did not ask for the sheet', () => {
    isPhone.value = true
    wrapper = mountPicker()
    expect(wrapper.find('input[data-testid="p"]').exists()).toBe(true)
    expect(wrapper.find('button[data-testid="p"]').exists()).toBe(false)
  })
})
