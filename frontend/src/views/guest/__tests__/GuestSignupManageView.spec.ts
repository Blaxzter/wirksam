// @vitest-environment jsdom
import { type VueWrapper, flushPromises, mount } from '@vue/test-utils'
import { type Component, defineComponent } from 'vue'

import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { type Router, RouterView, createRouter, createWebHistory } from 'vue-router'

import type {
  GuestSignupBooking,
  GuestSignupManage,
  GuestVoucherAccount,
  VoucherBalance,
} from '@/client/types.gen'
import i18n from '@/locales/i18n'
import GuestSignupManageView from '@/views/guest/GuestSignupManageView.vue'

/**
 * A guest's own page behind `/guest-signup#<token>`: the token is read from
 * the fragment once and taken out of the address bar (and out of the router's
 * own record of it) before anything else, and each action asks first. "Das war
 * ich nicht" is there only for a page opened from a mail. An action that
 * removes its own button leaves focus on what it changed.
 */

const holders = vi.hoisted(() => ({
  post: vi.fn(),
  confirm: vi.fn(),
  toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() },
}))

vi.mock('@/client/client.gen', () => ({ client: { get: vi.fn(), post: holders.post } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: null }) }))
vi.mock('vue-sonner', () => ({ toast: holders.toast }))
vi.mock('@/composables/useDialog', () => ({
  useDialog: () => ({ confirmDestructive: holders.confirm }),
}))

function booking(overrides: Partial<GuestSignupBooking> = {}): GuestSignupBooking {
  return {
    booking_id: 'booking-1',
    status: 'confirmed',
    event_name: 'Summer fair',
    task_name: 'Bar',
    date: '2026-11-20',
    start_time: '10:00:00',
    end_time: '12:00:00',
    location: 'Hall',
    can_cancel: true,
    reminder_on: true,
    ...overrides,
  }
}

function manageView(overrides: Partial<GuestSignupManage> = {}): GuestSignupManage {
  return {
    name: 'Anna Berg',
    email: 'anna@example.org',
    event: {
      name: 'Summer fair',
      start_date: '2026-11-20',
      end_date: '2026-11-21',
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    },
    bookings: [
      booking(),
      booking({ booking_id: 'booking-2', status: 'cancelled', task_name: 'Kitchen' }),
      booking({ booking_id: 'booking-3', can_cancel: false, task_name: 'Setup' }),
      booking({ booking_id: 'booking-4', event_name: 'Winter fair', task_name: 'Moved' }),
    ],
    can_set_reminders: true,
    confirmed: false,
    can_confirm: false,
    can_reject: false,
    reject_suppresses: true,
    has_phone: false,
    retention_days: 30,
    erase_on: '2026-12-22',
    vouchers: [],
    ...overrides,
  }
}

const mounted: VueWrapper[] = []
const routers: Router[] = []

/** The page under a real router on the browser's history, as in the app. */
async function mountPage(
  view: GuestSignupManage | Error = manageView(),
  hash = '#token-123',
  stubs: Record<string, Component> = {},
) {
  history.replaceState(null, '', `/guest-signup?from=mail${hash}`)
  if (view instanceof Error) holders.post.mockRejectedValueOnce(view)
  else holders.post.mockResolvedValueOnce({ data: view })
  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/guest-signup', name: 'guest-signup-manage', component: GuestSignupManageView },
      { path: '/privacy', name: 'privacy', component: defineComponent({ render: () => null }) },
    ],
  })
  routers.push(router)
  const wrapper = mount(RouterView, {
    attachTo: document.body,
    global: { plugins: [router, i18n], stubs },
  })
  mounted.push(wrapper)
  await router.isReady()
  await flushPromises()
  return { wrapper, router }
}

/** What the browser does when another link to this page is opened in the same tab. */
async function openInSameTab(url: string) {
  history.pushState(null, '', url)
  window.dispatchEvent(new PopStateEvent('popstate', { state: null }))
  await flushPromises()
}

const byTestId = (wrapper: VueWrapper, id: string) => wrapper.find(`[data-testid="${id}"]`)

function summary(overrides: Partial<VoucherBalance> = {}): VoucherBalance {
  return {
    user_id: 'guest-1',
    name: 'Anna Berg',
    earned: 4,
    upcoming: 0,
    redeemed: 1,
    adjusted: 0,
    available: 3,
    ...overrides,
  }
}

function voucherAccount(overrides: Partial<GuestVoucherAccount> = {}): GuestVoucherAccount {
  return {
    event_id: 'event-1',
    event_name: 'Summer fair',
    account: { summary: summary(), shifts: [], entries: [] },
    ...overrides,
  }
}

/** Stands in for a vouchers card: shows which event, and plays what its code screen reports. */
const VouchersCardStub = defineComponent({
  props: { voucher: { type: Object, required: true }, named: Boolean },
  emits: ['redeemed', 'gone'],
  template: `<section data-testid="vouchers-card-stub" :data-named="named">
    {{ voucher.event_name }}
    <button data-testid="stub-redeemed" @click="$emit('redeemed')" />
    <button data-testid="stub-gone" @click="$emit('gone')" />
  </section>`,
})
const lastPost = () => holders.post.mock.calls.at(-1)![0]

function apiError(status: number, code?: string) {
  return Object.assign(new Error(code), {
    isAxiosError: true,
    response: { status, data: { status, code } },
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  i18n.global.locale.value = 'en'
  holders.post.mockReset()
  holders.confirm.mockReset()
  for (const fn of Object.values(holders.toast)) fn.mockReset()
})

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount()
  for (const router of routers.splice(0)) router.options.history.destroy()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

describe('GuestSignupManageView: the link', () => {
  it('reads the token from the fragment and takes it out of the address bar', async () => {
    await mountPage()
    expect(window.location.hash).toBe('')
    expect(window.location.search).toBe('?from=mail')
    expect(history.state.current).toBe('/guest-signup?from=mail')
    expect(lastPost()).toEqual({
      url: '/public/guest-signups/manage',
      body: { token: 'token-123' },
      throwOnError: true,
    })
  })

  it('leaves no token in the history for the page opened next', async () => {
    const { router } = await mountPage()
    await router.push({ name: 'privacy' })
    expect(history.state.back).toBe('/guest-signup?from=mail')
    expect(JSON.stringify(history.state)).not.toContain('token-123')
  })

  it('opens a second link the same tab is sent to, which reloads nothing', async () => {
    const { wrapper } = await mountPage(manageView({ can_reject: false }))
    holders.post.mockResolvedValueOnce({ data: manageView({ can_reject: true }) })
    await openInSameTab('/guest-signup#token-456')
    expect(lastPost().body).toEqual({ token: 'token-456' })
    expect(window.location.hash).toBe('')
    expect(JSON.stringify(history.state)).not.toContain('token-456')
    expect(byTestId(wrapper, 'btn-guest-not-me').exists()).toBe(true)
  })

  it('leaves the page alone when the fragment is only cleared', async () => {
    await mountPage()
    await openInSameTab('/guest-signup#')
    expect(holders.post).toHaveBeenCalledTimes(1)
  })

  it('reads no fragment of another page as a link', async () => {
    const { router } = await mountPage()
    await router.push({ name: 'privacy', hash: '#cookies' })
    await flushPromises()
    expect(holders.post).toHaveBeenCalledTimes(1)
    expect(window.location.hash).toBe('#cookies')
  })

  it('shows a link without a token as one that does not work, without asking', async () => {
    const { wrapper } = await mountPage(manageView(), '')
    expect(byTestId(wrapper, 'guest-manage-not-found').exists()).toBe(true)
    expect(holders.post).not.toHaveBeenCalled()
  })

  it('shows a token the server does not know as one that does not work', async () => {
    const { wrapper } = await mountPage(apiError(404, 'guest_signup.not_found'))
    expect(byTestId(wrapper, 'page-heading').text()).toBe("This link doesn't work (any more)")
  })

  it('offers to try again with the same token after a failure', async () => {
    const { wrapper } = await mountPage(apiError(503))
    holders.post.mockResolvedValueOnce({ data: manageView() })
    await byTestId(wrapper, 'guest-manage-error').find('button').trigger('click')
    await flushPromises()
    expect(lastPost().body).toEqual({ token: 'token-123' })
    expect(byTestId(wrapper, 'guest-manage-page').exists()).toBe(true)
  })
})

describe('GuestSignupManageView: the page', () => {
  it('lists the shifts with what can still be done about each', async () => {
    const { wrapper } = await mountPage()
    expect(byTestId(wrapper, 'guest-manage-who').text()).toContain('Signed up as Anna Berg')
    const rows = wrapper.findAll('[data-testid="guest-manage-booking"]')
    expect(rows).toHaveLength(4)
    expect(byTestId(wrapper, 'btn-guest-cancel-booking-1').exists()).toBe(true)
    expect(rows[1]!.text()).toContain('Taken off')
    expect(byTestId(wrapper, 'btn-guest-cancel-booking-2').exists()).toBe(false)
    expect(rows[2]!.text()).toContain('Over')
    expect(byTestId(wrapper, 'btn-guest-cancel-booking-3').exists()).toBe(false)
    expect(rows[3]!.text()).toContain('Now part of Winter fair')
    expect(byTestId(wrapper, 'guest-demo-notice').exists()).toBe(false)
  })

  it('says that sign-ups through a demo’s list are a demo too', async () => {
    const demo = manageView()
    demo.event.is_sandbox = true
    const { wrapper } = await mountPage(demo)
    expect(byTestId(wrapper, 'guest-demo-notice').text()).toContain('Just a demo.')
  })

  it('says so when no shift is left', async () => {
    const { wrapper } = await mountPage(manageView({ bookings: [] }))
    expect(byTestId(wrapper, 'guest-manage-empty').exists()).toBe(true)
    expect(byTestId(wrapper, 'guest-reminders-switch').exists()).toBe(false)
  })

  it('takes the guest off a shift once they confirm', async () => {
    const { wrapper } = await mountPage()
    holders.confirm.mockResolvedValueOnce(false)
    await byTestId(wrapper, 'btn-guest-cancel-booking-1').trigger('click')
    await flushPromises()
    expect(holders.post).toHaveBeenCalledTimes(1)

    holders.confirm.mockResolvedValueOnce(true)
    holders.post.mockResolvedValueOnce({
      data: manageView({ bookings: [booking({ status: 'cancelled' })] }),
    })
    await byTestId(wrapper, 'btn-guest-cancel-booking-1').trigger('click')
    await flushPromises()
    expect(holders.confirm.mock.calls[1]![0].text).toContain('“Bar”')
    expect(lastPost()).toMatchObject({
      url: '/public/guest-signups/cancel',
      body: { token: 'token-123', booking_id: 'booking-1' },
    })
    expect(holders.toast.success).toHaveBeenCalledWith("You're no longer down for this shift.")
    expect(byTestId(wrapper, 'btn-guest-cancel-booking-1').exists()).toBe(false)
    // Its button went with it: focus is on the shift, not lost to the page.
    expect(document.activeElement?.id).toBe('guest-booking-booking-1')
  })

  it('names where focus goes if the confirmation closes after the shift was taken off', async () => {
    const { wrapper } = await mountPage()
    holders.confirm.mockResolvedValueOnce(true)
    holders.post.mockResolvedValueOnce({
      data: manageView({ bookings: [booking({ status: 'cancelled' })] }),
    })
    await byTestId(wrapper, 'btn-guest-cancel-booking-1').trigger('click')
    await flushPromises()
    ;(document.activeElement as HTMLElement).blur()

    holders.confirm.mock.calls[0]![0].focusInstead()
    expect(document.activeElement?.id).toBe('guest-booking-booking-1')
  })

  it('does not take a shift off twice while the first request runs', async () => {
    const { wrapper } = await mountPage()
    holders.confirm.mockResolvedValue(true)
    holders.post.mockReturnValueOnce(new Promise(() => {}))
    const button = byTestId(wrapper, 'btn-guest-cancel-booking-1')
    await button.trigger('click')
    await flushPromises()
    expect(button.attributes('aria-disabled')).toBe('true')
    await button.trigger('click')
    await flushPromises()
    expect(holders.confirm).toHaveBeenCalledTimes(1)
  })

  it('switches the reminders for the shifts still to come', async () => {
    const { wrapper } = await mountPage()
    const toggle = byTestId(wrapper, 'guest-reminders-switch')
    expect(toggle.attributes('data-state')).toBe('checked')
    holders.post.mockResolvedValueOnce({
      data: manageView({ bookings: [booking({ reminder_on: false })] }),
    })
    await toggle.trigger('click')
    await flushPromises()
    expect(lastPost()).toMatchObject({
      url: '/public/guest-signups/reminders',
      body: { enabled: false },
    })
    expect(byTestId(wrapper, 'guest-reminders-switch').attributes('data-state')).toBe('unchecked')
  })

  it('offers no reminder without an address', async () => {
    const { wrapper } = await mountPage(manageView({ email: null, can_set_reminders: false }))
    expect(byTestId(wrapper, 'guest-reminders-switch').exists()).toBe(false)
  })

  it('deletes the data once confirmed, and the page says so', async () => {
    const { wrapper } = await mountPage()
    holders.confirm.mockResolvedValueOnce(true)
    holders.post.mockResolvedValueOnce({ data: '' })
    await byTestId(wrapper, 'btn-guest-erase').trigger('click')
    await flushPromises()
    expect(lastPost().url).toBe('/public/guest-signups/erase')
    expect(byTestId(wrapper, 'guest-manage-erased').exists()).toBe(true)
    expect(document.activeElement).toBe(byTestId(wrapper, 'page-heading').element)
  })

  it('asks only once while deleting runs', async () => {
    const { wrapper } = await mountPage()
    holders.confirm.mockResolvedValue(true)
    holders.post.mockReturnValueOnce(new Promise(() => {}))
    await byTestId(wrapper, 'btn-guest-erase').trigger('click')
    await flushPromises()
    expect(byTestId(wrapper, 'btn-guest-not-me').exists()).toBe(false)
    expect(byTestId(wrapper, 'btn-guest-erase').attributes('aria-disabled')).toBe('true')
    await byTestId(wrapper, 'btn-guest-erase').trigger('click')
    await flushPromises()
    expect(holders.confirm).toHaveBeenCalledTimes(1)
  })

  it('keeps the data when the guest thinks again', async () => {
    const { wrapper } = await mountPage()
    holders.confirm.mockResolvedValueOnce(false)
    await byTestId(wrapper, 'btn-guest-erase').trigger('click')
    await flushPromises()
    expect(holders.post).toHaveBeenCalledTimes(1)
  })
})

describe('GuestSignupManageView: "Das war ich nicht"', () => {
  it('is not offered on the link the sign-up page showed', async () => {
    const { wrapper } = await mountPage(manageView({ can_reject: false }))
    expect(byTestId(wrapper, 'btn-guest-not-me').exists()).toBe(false)
  })

  it('is offered on the link from a mail, and ends on its own page', async () => {
    const { wrapper } = await mountPage(manageView({ can_reject: true }))
    holders.confirm.mockResolvedValueOnce(false)
    await byTestId(wrapper, 'btn-guest-not-me').trigger('click')
    await flushPromises()
    expect(holders.post).toHaveBeenCalledTimes(1)

    holders.confirm.mockResolvedValueOnce(true)
    holders.post.mockResolvedValueOnce({ data: '' })
    await byTestId(wrapper, 'btn-guest-not-me').trigger('click')
    await flushPromises()
    expect(holders.confirm.mock.calls[1]![0].text).toBe(
      'We delete the sign-up and never write to this address again.',
    )
    expect(lastPost()).toMatchObject({
      url: '/public/guest-signups/not-me',
      body: { token: 'token-123' },
    })
    expect(byTestId(wrapper, 'guest-manage-rejected').exists()).toBe(true)
    expect(document.activeElement).toBe(byTestId(wrapper, 'page-heading').element)
  })
})

describe('GuestSignupManageView: confirming the address', () => {
  const fromMail = (overrides: Partial<GuestSignupManage> = {}) =>
    manageView({ can_confirm: true, can_reject: true, ...overrides })

  it('offers "Ja, das bin ich" only on a link from a mail', async () => {
    const { wrapper } = await mountPage(fromMail())
    expect(byTestId(wrapper, 'guest-confirm').text()).toContain('Is this your address?')
    expect(byTestId(wrapper, 'guest-confirm-text').text()).toContain('Confirm anna@example.org.')
    // "Das war ich nicht" sits on the card, not twice on the page.
    expect(wrapper.findAll('[data-testid="btn-guest-not-me"]')).toHaveLength(1)
    expect(byTestId(wrapper, 'guest-manage-not-me').exists()).toBe(false)
    expect(byTestId(wrapper, 'guest-confirm-from-mail').exists()).toBe(false)
  })

  it('says where confirming happens on the link the sign-up page showed', async () => {
    const { wrapper } = await mountPage(manageView())
    expect(byTestId(wrapper, 'guest-confirm').exists()).toBe(false)
    expect(byTestId(wrapper, 'guest-confirm-from-mail').text()).toBe(
      'If we sent you an email, you can confirm your address through the link in it.',
    )
  })

  it('confirms, goes on with the account’s link and puts focus on what changed', async () => {
    const { wrapper } = await mountPage(fromMail())
    holders.post.mockResolvedValueOnce({
      data: {
        token: 'account-token',
        manage: manageView({ confirmed: true, can_confirm: false, can_reject: false }),
      },
    })
    await byTestId(wrapper, 'btn-guest-confirm').trigger('click')
    await flushPromises()

    expect(lastPost()).toEqual({
      url: '/public/guest-signups/confirm',
      body: { token: 'token-123' },
      throwOnError: true,
    })
    expect(holders.toast.success).toHaveBeenCalledWith(
      'Confirmed. This page now shows every sign-up you confirmed for “Summer fair”.',
    )
    expect(byTestId(wrapper, 'guest-confirm').exists()).toBe(false)
    expect(byTestId(wrapper, 'guest-manage-confirmed').text()).toBe('Address confirmed')
    expect(document.activeElement).toBe(byTestId(wrapper, 'guest-manage-confirmed').element)
    // Nothing is offered that the confirmed page no longer allows.
    expect(byTestId(wrapper, 'btn-guest-not-me').exists()).toBe(false)
    expect(byTestId(wrapper, 'guest-confirm-from-mail').exists()).toBe(false)

    holders.post.mockResolvedValueOnce({ data: manageView({ confirmed: true }) })
    await byTestId(wrapper, 'guest-reminders-switch').trigger('click')
    await flushPromises()
    expect(lastPost().body).toMatchObject({ token: 'account-token' })
  })

  it('sends one confirmation however often the button is pressed', async () => {
    const { wrapper } = await mountPage(fromMail())
    holders.post.mockReturnValueOnce(new Promise(() => {}))
    const button = byTestId(wrapper, 'btn-guest-confirm')
    await button.trigger('click')
    await flushPromises()
    expect(button.attributes('aria-disabled')).toBe('true')
    await button.trigger('click')
    await byTestId(wrapper, 'btn-guest-not-me').trigger('click')
    await flushPromises()
    expect(holders.post).toHaveBeenCalledTimes(2)
    expect(holders.confirm).not.toHaveBeenCalled()
  })

  it('says why a confirmation was refused, and keeps the card', async () => {
    const { wrapper } = await mountPage(fromMail())
    holders.post.mockRejectedValueOnce(apiError(429, 'guest_signup.rate_limited'))
    await byTestId(wrapper, 'btn-guest-confirm').trigger('click')
    await flushPromises()
    expect(holders.toast.success).not.toHaveBeenCalled()
    expect(byTestId(wrapper, 'guest-confirm').exists()).toBe(true)
  })

  it('ends on "link does not work" when the link died meanwhile, with focus there', async () => {
    const { wrapper } = await mountPage(fromMail())
    holders.post.mockRejectedValueOnce(apiError(404, 'guest_signup.not_found'))
    await byTestId(wrapper, 'btn-guest-confirm').trigger('click')
    await flushPromises()
    expect(byTestId(wrapper, 'guest-manage-not-found').exists()).toBe(true)
    expect(document.activeElement).toBe(byTestId(wrapper, 'page-heading').element)
  })

  it('says "Das war ich nicht" from the card, which ends the page', async () => {
    const { wrapper } = await mountPage(fromMail())
    holders.confirm.mockResolvedValueOnce(true)
    holders.post.mockResolvedValueOnce({ data: '' })
    await byTestId(wrapper, 'btn-guest-not-me').trigger('click')
    await flushPromises()
    expect(lastPost().url).toBe('/public/guest-signups/not-me')
    expect(byTestId(wrapper, 'guest-manage-rejected').exists()).toBe(true)
  })

  it('shows the sign-ups as confirmed when "Das war ich nicht" came after a confirmation elsewhere', async () => {
    // Another tab with the same mail link pressed "Ja, das bin ich" first.
    const { wrapper } = await mountPage(fromMail({ name: 'Zweite Kette' }))
    holders.confirm.mockResolvedValueOnce(true)
    holders.post
      .mockRejectedValueOnce(apiError(409, 'guest_signup.reject_confirmed'))
      .mockResolvedValueOnce({
        data: manageView({ confirmed: true, can_confirm: false, can_reject: false }),
      })
    const notMe = byTestId(wrapper, 'btn-guest-not-me')
    const button = notMe.element as HTMLButtonElement
    button.focus()
    await notMe.trigger('click')
    await flushPromises()

    expect(holders.toast.error).toHaveBeenCalled()
    expect(lastPost().url).toBe('/public/guest-signups/manage')
    expect(byTestId(wrapper, 'guest-confirm').exists()).toBe(false)
    expect(byTestId(wrapper, 'guest-manage-who').text()).toContain('Anna Berg')
    expect(document.activeElement).toBe(byTestId(wrapper, 'guest-manage-confirmed').element)
  })
})

describe('GuestSignupManageView: whose sign-ups, and when they go', () => {
  it('names a shift signed up for under another name than the page’s, and no other', async () => {
    const { wrapper } = await mountPage(
      manageView({
        confirmed: true,
        bookings: [
          booking({ name: 'Anna Berg' }),
          booking({ booking_id: 'booking-2', name: 'Tom Berg', show_first_name: true }),
          booking({ booking_id: 'booking-3', name: null }),
          booking({ booking_id: 'booking-4', can_cancel: false, show_first_name: true }),
        ],
      }),
    )
    const rows = wrapper.findAll('[data-testid="guest-manage-booking"]')
    expect(rows[0]!.find('[data-testid="guest-booking-name"]').exists()).toBe(false)
    expect(rows[1]!.find('[data-testid="guest-booking-name"]').text()).toBe('Signed up as Tom Berg')
    expect(rows[1]!.find('[data-testid="guest-booking-first-name"]').text()).toBe(
      'Your first name is shown for this shift on shared lists.',
    )
    expect(rows[0]!.find('[data-testid="guest-booking-first-name"]').exists()).toBe(false)
    expect(rows[2]!.find('[data-testid="guest-booking-name"]').exists()).toBe(false)
    // An over shift is on no list any more.
    expect(rows[3]!.find('[data-testid="guest-booking-first-name"]').exists()).toBe(false)
  })

  it('shows what a shift earns, while the sign-up stands', async () => {
    const { wrapper } = await mountPage(
      manageView({
        bookings: [
          booking({ vouchers: 2 }),
          booking({ booking_id: 'booking-2', status: 'cancelled', vouchers: 2 }),
          booking({ booking_id: 'booking-3' }),
        ],
      }),
    )
    const rows = wrapper.findAll('[data-testid="guest-manage-booking"]')
    expect(rows[0]!.find('[data-testid="guest-booking-vouchers"]').text()).toBe('2 vouchers')
    expect(rows[1]!.find('[data-testid="guest-booking-vouchers"]').exists()).toBe(false)
    expect(rows[2]!.find('[data-testid="guest-booking-vouchers"]').exists()).toBe(false)
  })

  it('says on which day the data goes, naming only what is stored', async () => {
    // A last shift on 20 November: kept through 4 December, gone on the 5th.
    // The sentence counts full days, so it agrees with the date it names.
    const plain = await mountPage(manageView({ retention_days: 14, erase_on: '2026-12-05' }))
    expect(byTestId(plain.wrapper, 'guest-manage-retention').text()).toBe(
      'On December 5, 2026 we delete your name and email address, once 14 full days have passed since your last shift.',
    )
    plain.wrapper.unmount()

    const phone = await mountPage(
      manageView({ email: null, has_phone: true, retention_days: 14, erase_on: '2026-12-05' }),
    )
    expect(byTestId(phone.wrapper, 'guest-manage-retention').text()).toContain(
      'we delete your name and phone number, once 14 full days',
    )
    phone.wrapper.unmount()

    const nothing = await mountPage(manageView({ email: null, retention_days: 1 }))
    expect(byTestId(nothing.wrapper, 'guest-manage-retention').text()).toContain(
      'we delete your name, once a full day has passed since your last shift.',
    )
  })

  it('says that unredeemed vouchers expire with the data', async () => {
    const { wrapper } = await mountPage(
      manageView({ has_phone: true, vouchers: [voucherAccount()] }),
      '#token-123',
      { GuestVouchersCard: VouchersCardStub },
    )
    expect(byTestId(wrapper, 'guest-manage-retention').text()).toMatch(
      /we delete your name, email address and phone number, once 30 full days have passed since your last shift\. Vouchers you have not redeemed by then expire\.$/,
    )
  })
})

describe('GuestSignupManageView: vouchers', () => {
  const stubs = { GuestVouchersCard: VouchersCardStub }

  it('shows no vouchers card while nothing earns any', async () => {
    const { wrapper } = await mountPage(manageView(), '#token-123', stubs)
    expect(byTestId(wrapper, 'vouchers-card-stub').exists()).toBe(false)
  })

  it('shows a card per event, each named once there are several', async () => {
    const one = await mountPage(manageView({ vouchers: [voucherAccount()] }), '#token-123', stubs)
    expect(byTestId(one.wrapper, 'vouchers-card-stub').attributes('data-named')).toBe('false')
    one.wrapper.unmount()

    const two = await mountPage(
      manageView({
        vouchers: [
          voucherAccount(),
          voucherAccount({ event_id: 'event-2', event_name: 'Winter fair' }),
        ],
      }),
      '#token-123',
      stubs,
    )
    const cards = two.wrapper.findAll('[data-testid="vouchers-card-stub"]')
    expect(cards.map((c) => c.text())).toEqual(['Summer fair', 'Winter fair'])
    expect(cards[0]!.attributes('data-named')).toBe('true')
  })

  it('reads the page again once a code was used', async () => {
    const { wrapper } = await mountPage(
      manageView({ vouchers: [voucherAccount()] }),
      '#token-123',
      stubs,
    )
    holders.post.mockResolvedValueOnce({ data: manageView({ name: 'Fresh' }) })
    await byTestId(wrapper, 'stub-redeemed').trigger('click')
    await flushPromises()
    expect(lastPost()).toMatchObject({ url: '/public/guest-signups/manage' })
    expect(byTestId(wrapper, 'guest-manage-who').text()).toContain('Fresh')
  })

  it('ends on "link does not work" once the code screen found the link dead', async () => {
    const { wrapper } = await mountPage(
      manageView({ vouchers: [voucherAccount()] }),
      '#token-123',
      stubs,
    )
    holders.post.mockRejectedValueOnce(apiError(404, 'guest_signup.not_found'))
    await byTestId(wrapper, 'stub-gone').trigger('click')
    await flushPromises()
    expect(byTestId(wrapper, 'guest-manage-not-found').exists()).toBe(true)
    expect(document.activeElement).toBe(byTestId(wrapper, 'page-heading').element)
  })

  it('names the vouchers that expire when the data is deleted', async () => {
    const { wrapper } = await mountPage(
      manageView({
        vouchers: [
          voucherAccount(),
          voucherAccount({
            event_id: 'event-2',
            account: { summary: summary({ available: 2 }), shifts: [], entries: [] },
          }),
        ],
      }),
      '#token-123',
      stubs,
    )
    holders.confirm.mockResolvedValueOnce(false)
    await byTestId(wrapper, 'btn-guest-erase').trigger('click')
    await flushPromises()
    const text = holders.confirm.mock.calls[0]![0].text as string
    expect(text).toContain('This link stops working. Your 5 unredeemed vouchers expire.')
    expect(text).not.toContain('sign-ups on this page')
  })
})

describe('GuestSignupManageView: deleting a confirmed address', () => {
  it('says that only the sign-ups on this page go', async () => {
    const { wrapper } = await mountPage(manageView({ confirmed: true }))
    holders.confirm.mockResolvedValueOnce(false)
    await byTestId(wrapper, 'btn-guest-erase').trigger('click')
    await flushPromises()
    const text = holders.confirm.mock.calls[0]![0].text as string
    expect(text).toContain('We delete the sign-ups on this page.')
    expect(text).not.toContain('unredeemed')
  })
})

describe('GuestSignupManageView: "Das war ich nicht" for an address confirmed elsewhere', () => {
  it('says mail about the confirmed sign-ups goes on, before and after', async () => {
    const { wrapper } = await mountPage(manageView({ can_reject: true, reject_suppresses: false }))
    expect(byTestId(wrapper, 'guest-manage-not-me').text()).toContain(
      'You keep getting email about the sign-ups you confirmed.',
    )
    expect(byTestId(wrapper, 'guest-manage-not-me').text()).not.toContain('never write')

    holders.confirm.mockResolvedValueOnce(true)
    holders.post.mockResolvedValueOnce({ data: '' })
    await byTestId(wrapper, 'btn-guest-not-me').trigger('click')
    await flushPromises()
    expect(holders.confirm.mock.calls[0]![0].text).toBe(
      'We delete this sign-up. You keep getting email about the sign-ups you confirmed.',
    )
    expect(byTestId(wrapper, 'guest-manage-rejected').text()).toContain(
      "We've deleted the sign-up. You keep getting email about the sign-ups you confirmed.",
    )
  })
})
