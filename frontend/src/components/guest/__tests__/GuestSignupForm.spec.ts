// @vitest-environment jsdom
import { type VueWrapper, flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useGuestSignupStore } from '@/stores/guestSignup'

import GuestSignupForm from '@/components/guest/GuestSignupForm.vue'

import type { PublicSharedList, PublicShift } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * The public sign-up form against the real store, with only the HTTP client
 * stubbed, so what is asserted is the request a guest's typing turns into:
 * the order the form complains in, the reminder that only exists with an
 * address, and the Turnstile token that is reset after every refusal and left
 * out when there is none.
 */

const holders = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  reset: vi.fn(),
}))

vi.mock('@/client/client.gen', () => ({ client: { get: holders.get, post: holders.post } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: null }) }))

/** Stands in for Cloudflare's widget: hands out a token on demand, records resets. */
const TurnstileStub = defineComponent({
  name: 'TurnstileWidget',
  emits: ['update:token'],
  setup(_, { emit, expose }) {
    expose({ reset: holders.reset })
    return () =>
      h('button', {
        type: 'button',
        'data-testid': 'solve-turnstile',
        onClick: () => emit('update:token', 'solved-token'),
      })
  },
})

const shift: PublicShift = {
  id: 'shift-1',
  task_id: 'task-1',
  task_name: 'Bar',
  location: 'Hall',
  start_time: '10:00:00',
  end_time: '12:00:00',
  capacity: 2,
  free: 2,
  full: false,
}

function publicList(overrides: Partial<PublicSharedList> = {}): PublicSharedList {
  return {
    code: 'abc123',
    title: 'Helpers wanted',
    status: 'live',
    event: {
      name: 'Summer fair',
      start_date: '2026-11-20',
      end_date: '2026-11-20',
      timezone: 'Europe/Berlin',
    },
    ask_email: 'required',
    ask_phone: 'optional',
    show_names: 'none',
    max_per_person: null,
    days: [{ date: '2026-11-20', shifts: [shift] }],
    // Not the hosted 30: the form must say what the server says.
    retention_days: 14,
    ...overrides,
  }
}

const mounted: { unmount: () => void }[] = []

async function mountForm(list = publicList(), picked: PublicShift = shift) {
  const store = useGuestSignupStore()
  holders.get.mockResolvedValueOnce({ data: list })
  await store.load(list.code)
  const wrapper = mount(GuestSignupForm, {
    props: { list, shift: picked, date: '2026-11-20' },
    attachTo: document.body,
    global: {
      plugins: [i18n],
      stubs: { TurnstileWidget: TurnstileStub, RouterLink: { template: '<a><slot /></a>' } },
    },
  })
  mounted.push(wrapper)
  return { wrapper, store }
}

const byTestId = (wrapper: VueWrapper, id: string) => wrapper.find(`[data-testid="${id}"]`)

async function submit(wrapper: VueWrapper) {
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

beforeEach(() => {
  setActivePinia(createPinia())
  i18n.global.locale.value = 'en'
  holders.get.mockReset()
  holders.post.mockReset()
  holders.reset.mockReset()
  delete globalThis.__APP_CONFIG__
})

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount()
  document.body.innerHTML = ''
  delete globalThis.__APP_CONFIG__
})

describe('GuestSignupForm', () => {
  it('names the shift and takes focus there, so a screen reader hears where it is', async () => {
    const { wrapper } = await mountForm()
    expect(byTestId(wrapper, 'guest-signup-summary').text()).toContain('Bar')
    expect(document.activeElement?.id).toBe('guest-signup-summary')
  })

  it('asks for the fields in the order the list wants them, marking "optional"', async () => {
    const { wrapper } = await mountForm(publicList({ ask_email: 'optional', ask_phone: 'off' }))
    expect(byTestId(wrapper, 'guest-input-name').exists()).toBe(true)
    expect(wrapper.find('label[for="guest-email"]').text()).toContain('optional')
    expect(byTestId(wrapper, 'guest-input-phone').exists()).toBe(false)
  })

  it('shows every refused field and puts the cursor on the first one in reading order', async () => {
    const { wrapper } = await mountForm(publicList({ ask_phone: 'required' }))
    await submit(wrapper)

    expect(byTestId(wrapper, 'guest-name-error').text()).toBe('Please enter your name.')
    expect(byTestId(wrapper, 'guest-email-error').text()).toContain('Please enter your email')
    expect(byTestId(wrapper, 'guest-phone-error').text()).toBe('Please enter a phone number.')
    expect(document.activeElement?.id).toBe('guest-name')
    expect(holders.post).not.toHaveBeenCalled()

    await byTestId(wrapper, 'guest-input-name').setValue('Anna Berg')
    await submit(wrapper)
    expect(byTestId(wrapper, 'guest-name-error').exists()).toBe(false)
    expect(document.activeElement?.id).toBe('guest-email')
    expect(document.getElementById('guest-email')?.getAttribute('aria-describedby')).toBe(
      'guest-email-hint guest-email-error',
    )
  })

  it('offers the reminder only once there is an address to send it to', async () => {
    const { wrapper } = await mountForm(publicList({ ask_email: 'optional' }))
    expect(byTestId(wrapper, 'guest-check-remind').exists()).toBe(false)
    await byTestId(wrapper, 'guest-input-email').setValue('anna@example.org')
    expect(byTestId(wrapper, 'guest-check-remind').attributes('data-state')).toBe('checked')
  })

  it('sends the reminder choice as ticked, and no reminder without an address', async () => {
    const { wrapper } = await mountForm(publicList({ ask_email: 'optional' }))
    await byTestId(wrapper, 'guest-input-name').setValue('Anna Berg')
    await byTestId(wrapper, 'guest-input-email').setValue('anna@example.org')
    await byTestId(wrapper, 'guest-check-remind').trigger('click')
    holders.post.mockResolvedValueOnce({ data: { guest_token: 't', shift } })
    await submit(wrapper)
    expect(holders.post.mock.calls[0]![0].body).toMatchObject({ remind: false })
  })

  it('leaves the Turnstile token out where the deployment has no bot check', async () => {
    const { wrapper } = await mountForm()
    expect(byTestId(wrapper, 'solve-turnstile').exists()).toBe(false)
    await byTestId(wrapper, 'guest-input-name').setValue('Anna Berg')
    await byTestId(wrapper, 'guest-input-email').setValue('anna@example.org')
    holders.post.mockResolvedValueOnce({ data: { guest_token: 't', shift } })
    await submit(wrapper)

    const body = holders.post.mock.calls[0]![0].body
    expect(body).not.toHaveProperty('turnstile_token')
    expect(body).toMatchObject({ shift_id: 'shift-1', show_names: 'none', remind: true })
    expect(wrapper.emitted('done')).toHaveLength(1)
  })

  it('waits for the bot check, sends its token, and resets it after a refusal', async () => {
    globalThis.__APP_CONFIG__ = { TURNSTILE_SITE_KEY: 'site-key' }
    const { wrapper } = await mountForm()
    const button = byTestId(wrapper, 'btn-guest-submit')
    expect(button.attributes('disabled')).toBeDefined()
    expect(byTestId(wrapper, 'guest-awaiting-check').exists()).toBe(true)

    await byTestId(wrapper, 'solve-turnstile').trigger('click')
    expect(button.attributes('disabled')).toBeUndefined()

    await byTestId(wrapper, 'guest-input-name').setValue('Anna Berg')
    await byTestId(wrapper, 'guest-input-email').setValue('anna@example.org')
    holders.post.mockRejectedValueOnce({
      isAxiosError: true,
      response: { status: 409, data: { status: 409, code: 'booking.slot_full' } },
    })
    holders.get.mockResolvedValueOnce({ data: publicList() })
    await submit(wrapper)

    expect(holders.post.mock.calls[0]![0].body.turnstile_token).toBe('solved-token')
    expect(holders.reset).toHaveBeenCalledTimes(1)
    expect(byTestId(wrapper, 'form-error').text()).toBe(
      'This shift has just filled up. Please pick another one.',
    )
    expect(wrapper.emitted('done')).toBeUndefined()
  })

  it('puts a field the server refused under that field', async () => {
    const { wrapper } = await mountForm()
    await byTestId(wrapper, 'guest-input-name').setValue('Anna Berg')
    await byTestId(wrapper, 'guest-input-email').setValue('anna@example.org')
    holders.post.mockRejectedValueOnce({
      isAxiosError: true,
      response: {
        status: 422,
        data: { status: 422, errors: [{ loc: ['body', 'name'], msg: 'x', type: 'value_error' }] },
      },
    })
    await submit(wrapper)
    expect(byTestId(wrapper, 'guest-name-error').text()).toBe('Please enter your name.')
    expect(document.activeElement?.id).toBe('guest-name')
    expect(byTestId(wrapper, 'form-error').exists()).toBe(false)
  })

  it('tells the guest who sees what, and that first names show where the list says so', async () => {
    const quiet = await mountForm()
    expect(byTestId(quiet.wrapper, 'guest-privacy-note').text()).not.toContain('first name')

    const named = await mountForm(publicList({ show_names: 'first' }))
    expect(byTestId(named.wrapper, 'guest-privacy-note').text()).toContain(
      'Your first name appears at this shift on shared lists that show first names.',
    )
    expect(byTestId(named.wrapper, 'guest-privacy-note').text()).toMatch(/More about privacy$/)
  })

  it('names only the contact details the list asks for when it says who sees them', async () => {
    const note = async (ask_email: 'off' | 'optional', ask_phone: 'off' | 'optional') => {
      const { wrapper } = await mountForm(publicList({ ask_email, ask_phone }))
      return byTestId(wrapper, 'guest-privacy-note').text()
    }
    const seenBy = 'Only the people in charge of this task and the organisers see your'

    expect(await note('optional', 'optional')).toContain(`${seenBy} email address and phone number.`)
    expect(await note('optional', 'off')).toContain(`${seenBy} email address.`)
    expect(await note('off', 'optional')).toContain(`${seenBy} phone number.`)
    const nameOnly = await note('off', 'off')
    expect(nameOnly).toContain('The helpers of this event see your name at the shift.')
    expect(nameOnly).not.toContain(seenBy)
  })

  it('says how long the details are kept, with the server’s number of days', async () => {
    const { wrapper } = await mountForm()
    const note = byTestId(wrapper, 'guest-privacy-note').text()
    expect(note).toContain(
      'We delete your name, email address and phone number 14 days after your last shift.',
    )
    expect(note).not.toContain('30')
    expect(note).not.toContain('voucher')
  })

  it('names only what the list asks for in the retention line', async () => {
    const nothing = await mountForm(publicList({ ask_email: 'off', ask_phone: 'off' }))
    const note = byTestId(nothing.wrapper, 'guest-privacy-note').text()
    expect(note).toContain('We delete your name 14 days after your last shift.')
    expect(note).not.toMatch(/delete your name(,| and) /)

    const emailOnly = await mountForm(publicList({ ask_phone: 'off' }))
    expect(byTestId(emailOnly.wrapper, 'guest-privacy-note').text()).toContain(
      'We delete your name and email address 14 days',
    )
    const phoneOnly = await mountForm(publicList({ ask_email: 'off', ask_phone: 'required' }))
    expect(byTestId(phoneOnly.wrapper, 'guest-privacy-note').text()).toContain(
      'We delete your name and phone number 14 days',
    )
  })

  it('says one day, not "1 days"', async () => {
    const { wrapper } = await mountForm(publicList({ retention_days: 1, ask_phone: 'off' }))
    expect(byTestId(wrapper, 'guest-privacy-note').text()).toContain(
      'We delete your name and email address one day after your last shift.',
    )
  })

  it('says what a shift with vouchers earns, and that unredeemed ones expire', async () => {
    const plain = await mountForm()
    expect(byTestId(plain.wrapper, 'guest-signup-vouchers').exists()).toBe(false)

    const { wrapper } = await mountForm(publicList(), { ...shift, vouchers: 2 })
    expect(byTestId(wrapper, 'guest-signup-vouchers').text()).toBe(
      'This shift earns 2 vouchers once it is over.',
    )
    expect(byTestId(wrapper, 'guest-privacy-note').text()).toContain(
      'Vouchers you have not redeemed by then expire.',
    )
  })

  it('reads in German, with du', async () => {
    i18n.global.locale.value = 'de'
    const { wrapper } = await mountForm(publicList(), { ...shift, vouchers: 1 })
    expect(byTestId(wrapper, 'guest-signup-vouchers').text()).toBe(
      'Für diese Schicht bekommst du 1 Marke, sobald sie vorbei ist.',
    )
    expect(byTestId(wrapper, 'guest-privacy-note').text()).toContain(
      'Wir löschen deinen Namen, deine E-Mail-Adresse und deine Telefonnummer 14 Tage nach deiner letzten Schicht.',
    )
  })

  it('goes back to the list', async () => {
    const { wrapper } = await mountForm()
    await byTestId(wrapper, 'btn-guest-back').trigger('click')
    expect(wrapper.emitted('back')).toHaveLength(1)
  })
})
