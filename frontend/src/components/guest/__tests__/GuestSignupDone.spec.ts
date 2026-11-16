// @vitest-environment jsdom
import { type VueWrapper, flushPromises, mount } from '@vue/test-utils'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import GuestSignupDone from '@/components/guest/GuestSignupDone.vue'

import type { PublicSharedList, PublicShift, PublicSignupResult } from '@/client/types.gen'
import { IDLE_RESET_MS } from '@/lib/guest-signup'
import i18n from '@/locales/i18n'

/**
 * The done step: how the guest gets back to their sign-up, what they can do
 * next, and the hand-over on a shared device. The clearing itself is the
 * store's (`stores/__tests__/guestSignup.spec.ts`) and the page's
 * (`SharedListPublicView.spec.ts`); this step only has to ask for it, on the
 * button and after two quiet minutes.
 */

const toast = vi.hoisted(() => ({ success: vi.fn(), info: vi.fn() }))
vi.mock('vue-sonner', () => ({ toast }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: null }) }))

const SHIFT: PublicShift = {
  id: 'shift-1',
  task_id: 'task-1',
  task_name: 'Bar',
  location: 'Hall',
  start_time: '10:00:00',
  end_time: '12:00:00',
  capacity: 2,
  free: 1,
  full: false,
}

function list(overrides: Partial<PublicSharedList> = {}): PublicSharedList {
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
    ask_phone: 'off',
    show_names: 'none',
    max_per_person: null,
    days: [{ date: '2026-11-20', shifts: [SHIFT] }],
    // Not the hosted 30: the page must say what the server says.
    retention_days: 14,
    ...overrides,
  }
}

function result(overrides: Partial<PublicSignupResult> = {}): PublicSignupResult {
  return {
    booking_id: 'booking-1',
    guest_token: 'guest-token',
    shift: SHIFT,
    date: '2026-11-20',
    email: 'anna@example.org',
    mail_queued: true,
    show_manage_link: false,
    remaining: null,
    ...overrides,
  }
}

type Props = {
  result: PublicSignupResult
  list: PublicSharedList
  mailedTo: string | null
  linkToKeep: string | null
  undoing?: boolean
}

const mounted: VueWrapper[] = []

function mountDone(props: Partial<Props> = {}) {
  const wrapper = mount(GuestSignupDone, {
    props: {
      result: result(),
      list: list(),
      mailedTo: 'anna@example.org',
      linkToKeep: null,
      ...props,
    },
    attachTo: document.body,
    global: { plugins: [i18n] },
  })
  mounted.push(wrapper)
  return wrapper
}

const byTestId = (wrapper: VueWrapper, id: string) => wrapper.find(`[data-testid="${id}"]`)

beforeEach(() => {
  i18n.global.locale.value = 'en'
  toast.success.mockReset()
  toast.info.mockReset()
})

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount()
  document.body.innerHTML = ''
  vi.useRealTimers()
})

describe('GuestSignupDone', () => {
  it('says the guest is signed up, for which shift, and takes focus there', () => {
    const wrapper = mountDone()
    expect(wrapper.find('h2').text()).toBe("You're signed up")
    expect(byTestId(wrapper, 'guest-done-shift').text()).toContain('Bar')
    expect(document.activeElement).toBe(wrapper.find('h2').element)
  })

  it('points to the mail when one went out, and to the same mail for later shifts', async () => {
    const wrapper = mountDone()
    expect(byTestId(wrapper, 'guest-done-mail').text()).toContain(
      "We've sent an email to anna@example.org. The link in it lets you take your name off again.",
    )
    expect(byTestId(wrapper, 'guest-done-keep-link').exists()).toBe(false)

    await wrapper.setProps({ result: result({ mail_queued: false }) })
    expect(byTestId(wrapper, 'guest-done-mail').text()).toContain(
      'lets you take your name off this shift too',
    )
  })

  it('shows the manage link to keep only when no mail carries it', async () => {
    const wrapper = mountDone({
      result: result({ email: null, mail_queued: false, show_manage_link: true }),
      mailedTo: null,
      linkToKeep: 'guest-token',
    })
    expect(byTestId(wrapper, 'guest-done-mail').exists()).toBe(false)
    const link = byTestId(wrapper, 'guest-manage-link').element as HTMLInputElement
    expect(link.value).toBe(`${window.location.origin}/guest-signup#guest-token`)
  })

  it('copies the link, and shows it to copy by hand where the clipboard is blocked', async () => {
    const writeText = vi
      .fn()
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error('no'))
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const wrapper = mountDone({ mailedTo: null, linkToKeep: 'guest-token' })
    const url = `${window.location.origin}/guest-signup#guest-token`

    await byTestId(wrapper, 'btn-copy-manage-link').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith(url)
    expect(toast.success).toHaveBeenCalledWith('Link copied')

    await byTestId(wrapper, 'btn-copy-manage-link').trigger('click')
    await flushPromises()
    expect(toast.info).toHaveBeenCalledWith(url)
  })

  it('offers another shift while the list allows one, and says so when it does not', async () => {
    const wrapper = mountDone({ result: result({ remaining: 1 }) })
    await byTestId(wrapper, 'btn-guest-another').trigger('click')
    expect(wrapper.emitted('another')).toHaveLength(1)

    await wrapper.setProps({ result: result({ remaining: 0 }) })
    expect(byTestId(wrapper, 'btn-guest-another').exists()).toBe(false)
    expect(byTestId(wrapper, 'guest-done-no-more').exists()).toBe(true)
  })

  it('asks to undo, and holds the button while that is under way, keeping focus on it', async () => {
    const wrapper = mountDone()
    const undo = byTestId(wrapper, 'btn-guest-undo')
    await undo.trigger('click')
    expect(wrapper.emitted('undo')).toHaveLength(1)

    const button = undo.element as HTMLButtonElement
    button.focus()
    await wrapper.setProps({ undoing: true })
    // aria-disabled, not disabled: a refused undo leaves focus where it was.
    expect(undo.attributes('disabled')).toBeUndefined()
    expect(undo.attributes('aria-disabled')).toBe('true')
    expect(document.activeElement).toBe(button)
    await undo.trigger('click')
    expect(wrapper.emitted('undo')).toHaveLength(1)
  })

  it('hands over to the next person on the button', async () => {
    const wrapper = mountDone()
    await byTestId(wrapper, 'btn-guest-next').trigger('click')
    expect(wrapper.emitted('next')).toHaveLength(1)
  })

  it('hands over by itself after two minutes without a touch, and not before', async () => {
    vi.useFakeTimers()
    const wrapper = mountDone()
    vi.advanceTimersByTime(IDLE_RESET_MS - 1_000)
    await flushPromises()
    expect(wrapper.emitted('next')).toBeUndefined()

    // A touch starts the two minutes again.
    window.dispatchEvent(new Event('mousemove'))
    vi.advanceTimersByTime(IDLE_RESET_MS - 1_000)
    await flushPromises()
    expect(wrapper.emitted('next')).toBeUndefined()

    vi.advanceTimersByTime(1_000)
    await flushPromises()
    expect(wrapper.emitted('next')).toHaveLength(1)
  })

  it('asks the guest not to pass the link on, under the mail and under the link', async () => {
    const mailed = mountDone()
    expect(byTestId(mailed, 'guest-done-mail').text()).toContain(
      "Anyone with this link can change your sign-ups. Don't pass it on.",
    )
    expect(byTestId(mailed, 'guest-done-link-private').exists()).toBe(true)

    const shown = mountDone({
      result: result({ email: null, mail_queued: false, show_manage_link: true }),
      mailedTo: null,
      linkToKeep: 'guest-token',
    })
    expect(byTestId(shown, 'guest-done-keep-link').text()).toContain(
      "Anyone with this link can change your sign-ups. Don't pass it on.",
    )
    expect(shown.findAll('[data-testid="guest-done-link-private"]')).toHaveLength(1)
  })

  it('says how long the details are kept, naming what the list asks for', () => {
    const wrapper = mountDone()
    expect(byTestId(wrapper, 'guest-done-retention').text()).toBe(
      'We delete your name and email address 14 days after your last shift.',
    )
    const none = mountDone({ list: list({ ask_email: 'off', ask_phone: 'off' }) })
    expect(byTestId(none, 'guest-done-retention').text()).toBe(
      'We delete your name 14 days after your last shift.',
    )
  })

  it('names no number of days but the server’s', () => {
    const wrapper = mountDone({ result: result({ shift: { ...SHIFT, vouchers: 3 } }) })
    expect(wrapper.text()).not.toContain('30')
  })

  it('says what a shift with vouchers earns, and where to redeem them', async () => {
    const plain = mountDone()
    expect(byTestId(plain, 'guest-done-vouchers').exists()).toBe(false)

    const earning = result({ shift: { ...SHIFT, vouchers: 2 } })
    const mailed = mountDone({ result: earning })
    expect(byTestId(mailed, 'guest-done-vouchers').text()).toContain(
      'This shift earns 2 vouchers once it is over.',
    )
    expect(byTestId(mailed, 'guest-done-redeem').text()).toBe(
      'To redeem them at a stand, open the link in the email and tap “Show code”.',
    )
    expect(byTestId(mailed, 'guest-done-mail').text()).toContain(
      "Anyone with this link can change your sign-ups and redeem your vouchers. Don't pass it on.",
    )
    expect(byTestId(mailed, 'guest-done-retention').text()).toBe(
      'We delete your name and email address 14 days after your last shift. Vouchers you have not redeemed by then expire.',
    )

    const shown = mountDone({
      result: { ...earning, email: null, mail_queued: false, show_manage_link: true },
      mailedTo: null,
      linkToKeep: 'guest-token',
    })
    expect(byTestId(shown, 'guest-done-redeem').text()).toBe(
      'To redeem them at a stand, open the link below and tap “Show code”.',
    )
    const keepLink = byTestId(shown, 'guest-done-keep-link')
    expect(keepLink.text()).toContain(
      "Save this link. It's your only way to take your name off again and to redeem your vouchers.",
    )
    // "Below" is where the link is.
    expect(
      byTestId(shown, 'guest-done-redeem').element.compareDocumentPosition(keepLink.element) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })

  it('has no way to redeem to name when neither a mail nor a link went out', () => {
    const wrapper = mountDone({
      result: result({ shift: { ...SHIFT, vouchers: 1 } }),
      mailedTo: null,
      linkToKeep: null,
    })
    expect(byTestId(wrapper, 'guest-done-vouchers').text()).toContain('1 voucher')
    expect(byTestId(wrapper, 'guest-done-redeem').exists()).toBe(false)
  })
})
