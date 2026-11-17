// @vitest-environment jsdom
import { type VueWrapper, flushPromises, mount } from '@vue/test-utils'

import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useGuestSignupStore } from '@/stores/guestSignup'

import type { PublicSharedList, PublicShift, PublicSignupResult } from '@/client/types.gen'
import { IDLE_RESET_MS } from '@/lib/guest-signup'
import i18n from '@/locales/i18n'
import SharedListPublicView from '@/views/guest/SharedListPublicView.vue'

/**
 * A shared list's public page end to end, with the real store and steps and
 * only the HTTP client stubbed: what strangers are shown of an organiser's
 * text, which state a list is in, and the walk from a shift to "signed up"
 * and back for the next person, who must find nothing of the last one.
 */

const holders = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  auth: { isAuthenticated: false, profile: null as { name: string } | null },
  toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() },
}))

vi.mock('@/client/client.gen', () => ({ client: { get: holders.get, post: holders.post } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => holders.auth }))
vi.mock('vue-sonner', () => ({ toast: holders.toast }))
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => ({ params: { code: 'abc123' } }),
}))

function shift(overrides: Partial<PublicShift> = {}): PublicShift {
  return {
    id: 'shift-1',
    task_id: 'task-1',
    task_name: 'Bar',
    location: 'Hall',
    start_time: '10:00:00',
    end_time: '12:00:00',
    capacity: 2,
    free: 2,
    full: false,
    names: [],
    others_count: 0,
    ...overrides,
  }
}

function publicList(overrides: Partial<PublicSharedList> = {}): PublicSharedList {
  return {
    code: 'abc123',
    title: 'Helpers wanted',
    intro: null,
    status: 'live',
    event: {
      name: 'Summer fair',
      start_date: '2026-11-20',
      end_date: '2026-11-21',
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    },
    ask_email: 'optional',
    ask_phone: 'off',
    show_names: 'none',
    max_per_person: null,
    days: [
      { date: '2026-11-20', shifts: [shift(), shift({ id: 'shift-2', free: 0, full: true })] },
    ],
    retention_days: 30,
    ...overrides,
  }
}

function signupResult(overrides: Partial<PublicSignupResult> = {}): PublicSignupResult {
  return {
    booking_id: 'booking-1',
    guest_token: 'guest-token',
    shift: shift({ free: 1 }),
    date: '2026-11-20',
    email: null,
    mail_queued: false,
    show_manage_link: true,
    remaining: null,
    ...overrides,
  }
}

const mounted: VueWrapper[] = []

async function mountPage(list: PublicSharedList | Error = publicList()) {
  if (list instanceof Error) holders.get.mockRejectedValueOnce(list)
  else holders.get.mockResolvedValue({ data: list })
  const wrapper = mount(SharedListPublicView, {
    attachTo: document.body,
    global: { plugins: [i18n], stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
  mounted.push(wrapper)
  await flushPromises()
  return wrapper
}

const byTestId = (wrapper: VueWrapper, id: string) => wrapper.find(`[data-testid="${id}"]`)

/** Pick the first shift, type a name and send. */
async function signUp(wrapper: VueWrapper, result = signupResult()) {
  await byTestId(wrapper, 'btn-pick-shift-shift-1').trigger('click')
  await byTestId(wrapper, 'guest-input-name').setValue('Anna Berg')
  holders.post.mockResolvedValueOnce({ data: result })
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

function apiError(status: number, code?: string) {
  return Object.assign(new Error(code), {
    isAxiosError: true,
    response: { status, data: { status, code } },
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  i18n.global.locale.value = 'en'
  holders.get.mockReset()
  holders.post.mockReset()
  holders.auth.isAuthenticated = false
  holders.auth.profile = null
  for (const fn of Object.values(holders.toast)) fn.mockReset()
  window.scrollTo = vi.fn()
})

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount()
  document.body.innerHTML = ''
  vi.useRealTimers()
})

describe('SharedListPublicView: what the page shows', () => {
  it('renders an intro with a link and markup as the literal text the organiser typed', async () => {
    const intro = 'Read https://evil.example/login first.\n<b>Bold</b> <a href="x">click</a>'
    const wrapper = await mountPage(publicList({ intro }))

    const shown = byTestId(wrapper, 'shared-list-intro')
    expect(shown.element.textContent?.trim()).toBe(intro)
    expect(shown.find('a').exists()).toBe(false)
    expect(shown.find('b').exists()).toBe(false)
    expect(shown.classes()).toContain('whitespace-pre-line')
  })

  it('heads the page with the list title, its event and its days', async () => {
    const wrapper = await mountPage()
    expect(byTestId(wrapper, 'page-heading').element.tagName).toBe('H1')
    expect(byTestId(wrapper, 'page-heading').text()).toBe('Helpers wanted')
    expect(byTestId(wrapper, 'shared-list-event').text()).toContain('Summer fair')
    expect(document.querySelector('[data-testid="guest-demo-notice"]')).toBeNull()
  })

  it('says in the header that a demo’s list mails nobody and goes with the demo', async () => {
    // The layout's header slot, which the note is teleported into.
    document.body.insertAdjacentHTML('afterbegin', '<div id="guest-header-slot"></div>')
    const demo = publicList()
    demo.event.is_sandbox = true
    const wrapper = await mountPage(demo)

    expect(wrapper.find('[data-testid="guest-demo-notice"]').exists()).toBe(false)
    const pill = document.querySelector<HTMLElement>(
      '#guest-header-slot [data-testid="guest-demo-notice"]',
    )
    expect(pill?.textContent?.trim()).toBe('Demo')
    pill!.click()
    await flushPromises()
    expect(document.querySelector('[data-testid="guest-demo-notice-text"]')?.textContent).toBe(
      'Just a demo.You can sign up here to try it out, but no mail is sent, not even to the address you give, and everything is deleted along with the demo.',
    )
  })

  it('lists the shifts with their free places, a full one without a way in', async () => {
    const wrapper = await mountPage()
    const shifts = wrapper.findAll('[data-testid="public-shift"]')
    expect(shifts).toHaveLength(2)
    expect(shifts[0]!.text()).toContain('2 free')
    expect(shifts[1]!.text()).toContain('full')
    expect(byTestId(wrapper, 'btn-pick-shift-shift-2').attributes('disabled')).toBeDefined()
    expect(byTestId(wrapper, 'btn-pick-shift-shift-1').attributes('aria-label')).toMatch(
      /^Sign up: Bar, /,
    )
  })

  it('names those who agreed, and only while the list shows first names', async () => {
    const named = shift({ names: ['Anna', 'Ben'], others_count: 2 })
    const shown = await mountPage(
      publicList({ show_names: 'first', days: [{ date: '2026-11-20', shifts: [named] }] }),
    )
    expect(byTestId(shown, 'public-shift-names').text()).toBe('Joining: Anna, Ben and 2 more')

    const hidden = await mountPage(publicList({ days: [{ date: '2026-11-20', shifts: [named] }] }))
    expect(byTestId(hidden, 'public-shift-names').exists()).toBe(false)
  })

  it('says what each shift earns, and that guests earn it too, when the task gives vouchers', async () => {
    const plain = await mountPage()
    expect(byTestId(plain, 'shared-list-vouchers-hint').exists()).toBe(false)
    expect(byTestId(plain, 'public-shift-vouchers').exists()).toBe(false)

    const earning = await mountPage(
      publicList({
        days: [{ date: '2026-11-20', shifts: [shift({ vouchers: 2 }), shift({ id: 'shift-2' })] }],
      }),
    )
    expect(byTestId(earning, 'shared-list-vouchers-hint').text()).toBe(
      'Shifts with vouchers earn them once the shift is over, also without an account.',
    )
    const shifts = earning.findAll('[data-testid="public-shift"]')
    expect(shifts[0]!.find('[data-testid="public-shift-vouchers"]').text()).toBe('2 vouchers')
    expect(shifts[1]!.find('[data-testid="public-shift-vouchers"]').exists()).toBe(false)
  })

  it('carries what the shift earns and how long data is kept through to the done step', async () => {
    const wrapper = await mountPage(
      publicList({
        retention_days: 14,
        days: [{ date: '2026-11-20', shifts: [shift({ vouchers: 1 })] }],
      }),
    )
    await signUp(wrapper, signupResult({ shift: shift({ free: 1, vouchers: 1 }) }))
    expect(byTestId(wrapper, 'guest-done-vouchers').text()).toContain('1 voucher')
    expect(byTestId(wrapper, 'guest-done-retention').text()).toContain(
      'We delete your name and email address 14 days after your last shift.',
    )
  })

  it('says how many shifts one person may take', async () => {
    const wrapper = await mountPage(publicList({ max_per_person: 2 }))
    expect(byTestId(wrapper, 'shared-list-max').text()).toBe(
      'You can sign up for up to 2 shifts on this list.',
    )
  })

  it.each([
    ['paused', 'shared-list-paused', "You can't sign up here right now"],
    ['closed', 'shared-list-closed', 'This list is closed'],
  ] as const)('shows a %s list as such, under its title', async (status, testid, title) => {
    const wrapper = await mountPage(publicList({ status, days: [] }))
    expect(byTestId(wrapper, testid).text()).toContain(title)
    expect(byTestId(wrapper, 'page-heading').text()).toBe('Helpers wanted')
    expect(byTestId(wrapper, 'public-shift-list').exists()).toBe(false)
  })

  it('narrows the shifts to those with a place left, and offers them all back', async () => {
    const wrapper = await mountPage()
    // One task on one day: only "with a place left" can narrow anything.
    expect(byTestId(wrapper, 'public-filter-task').exists()).toBe(false)
    expect(byTestId(wrapper, 'public-filter-day').exists()).toBe(false)

    await byTestId(wrapper, 'public-filter-free').trigger('click')
    expect(
      wrapper.findAll('[data-testid="public-shift"]').map((s) => s.attributes('data-shift-id')),
    ).toEqual(['shift-1'])

    const full = await mountPage(
      publicList({
        days: [{ date: '2026-11-20', shifts: [shift({ id: 'shift-2', free: 0, full: true })] }],
      }),
    )
    await byTestId(full, 'public-filter-free').trigger('click')
    expect(byTestId(full, 'shared-list-filtered-empty').text()).toContain('No shift matches.')
    await byTestId(full, 'shared-list-filtered-empty').find('button').trigger('click')
    expect(full.findAll('[data-testid="public-shift"]')).toHaveLength(1)
  })

  it('offers a task and a day filter once there is more than one of each', async () => {
    const wrapper = await mountPage(
      publicList({
        days: [
          {
            date: '2026-11-20',
            shifts: [shift(), shift({ id: 'shift-2', task_id: 'task-2', task_name: 'Grill' })],
          },
          { date: '2026-11-21', shifts: [shift({ id: 'shift-3' })] },
        ],
      }),
    )
    expect(byTestId(wrapper, 'public-filter-task').text()).toBe('All tasks')
    expect(byTestId(wrapper, 'public-filter-day').text()).toBe('All days')
    expect(byTestId(wrapper, 'public-filter-free').exists()).toBe(false)
  })

  it('says when a live list has no shifts left', async () => {
    const wrapper = await mountPage(publicList({ days: [] }))
    expect(byTestId(wrapper, 'shared-list-empty').exists()).toBe(true)
  })

  it('shows a link that leads nowhere as its own page', async () => {
    const wrapper = await mountPage(apiError(404, 'shared_list.not_found'))
    expect(byTestId(wrapper, 'shared-list-not-found').exists()).toBe(true)
    expect(byTestId(wrapper, 'page-heading').text()).toBe("This link doesn't exist (any more)")
  })

  it('offers to try again when the list could not be loaded', async () => {
    const wrapper = await mountPage(apiError(500))
    expect(byTestId(wrapper, 'shared-list-error').exists()).toBe(true)
    holders.get.mockResolvedValueOnce({ data: publicList() })
    await byTestId(wrapper, 'shared-list-error').find('button').trigger('click')
    await flushPromises()
    expect(byTestId(wrapper, 'public-shift-list').exists()).toBe(true)
  })

  it('tells a signed-in visitor they sign up without their account, and fills in nothing', async () => {
    holders.auth.isAuthenticated = true
    holders.auth.profile = { name: 'Olga Organiser' }
    const wrapper = await mountPage()
    expect(byTestId(wrapper, 'guest-signed-in').text()).toContain('Signed in as Olga Organiser')
    await byTestId(wrapper, 'btn-pick-shift-shift-1').trigger('click')
    expect((byTestId(wrapper, 'guest-input-name').element as HTMLInputElement).value).toBe('')
  })
})

describe('SharedListPublicView: signing up', () => {
  it('walks from a shift to the form and back', async () => {
    const wrapper = await mountPage()
    await byTestId(wrapper, 'btn-pick-shift-shift-1').trigger('click')
    expect(byTestId(wrapper, 'guest-signup-form').exists()).toBe(true)
    await byTestId(wrapper, 'btn-guest-back').trigger('click')
    await flushPromises()
    expect(byTestId(wrapper, 'public-shift-list').exists()).toBe(true)
    expect(document.activeElement).toBe(byTestId(wrapper, 'page-heading').element)
  })

  it('ends on the done step, with the link to keep when no mail went out', async () => {
    const wrapper = await mountPage()
    await signUp(wrapper)
    expect(byTestId(wrapper, 'guest-signup-done').exists()).toBe(true)
    expect(byTestId(wrapper, 'guest-manage-link').exists()).toBe(true)
  })

  it('keeps the name for another shift of the same chain', async () => {
    const wrapper = await mountPage()
    await signUp(wrapper)
    await byTestId(wrapper, 'btn-guest-another').trigger('click')
    await flushPromises()
    await byTestId(wrapper, 'btn-pick-shift-shift-1').trigger('click')
    expect((byTestId(wrapper, 'guest-input-name').element as HTMLInputElement).value).toBe(
      'Anna Berg',
    )
  })

  it('hands the next person an empty form and no way back to the last sign-up', async () => {
    const wrapper = await mountPage()
    await byTestId(wrapper, 'public-filter-free').trigger('click')
    await signUp(wrapper)
    await byTestId(wrapper, 'btn-guest-next').trigger('click')
    await flushPromises()

    const store = useGuestSignupStore()
    expect(store.fields).toEqual({ name: '', email: '', phone: '', remind: true })
    expect(store.linkToKeep).toBeNull()
    expect(store.last).toBeNull()
    expect(byTestId(wrapper, 'public-shift-list').exists()).toBe(true)
    // Nor the filter the last person chose.
    expect(wrapper.findAll('[data-testid="public-shift"]')).toHaveLength(2)
    expect(document.activeElement).toBe(byTestId(wrapper, 'page-heading').element)
  })

  it('does the same by itself when the done step is left alone for two minutes', async () => {
    const wrapper = await mountPage()
    await signUp(wrapper)
    vi.useFakeTimers()
    // The timer starts with the step, so remount it under the fake clock.
    await byTestId(wrapper, 'btn-guest-another').trigger('click')
    await flushPromises()
    await byTestId(wrapper, 'btn-pick-shift-shift-1').trigger('click')
    holders.post.mockResolvedValueOnce({ data: signupResult({ booking_id: 'booking-2' }) })
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(byTestId(wrapper, 'guest-signup-done').exists()).toBe(true)

    vi.advanceTimersByTime(IDLE_RESET_MS)
    await flushPromises()

    expect(byTestId(wrapper, 'guest-signup-done').exists()).toBe(false)
    expect(useGuestSignupStore().fields.name).toBe('')
  })

  it('takes a sign-up back and returns to the list', async () => {
    const wrapper = await mountPage()
    await signUp(wrapper)
    holders.post.mockResolvedValueOnce({ data: {} })
    await byTestId(wrapper, 'btn-guest-undo').trigger('click')
    await flushPromises()
    expect(holders.post.mock.calls.at(-1)![0].url).toBe('/public/guest-signups/cancel')
    expect(holders.toast.success).toHaveBeenCalledWith('Your sign-up has been undone.')
    expect(byTestId(wrapper, 'public-shift-list').exists()).toBe(true)
  })

  it('stays on the done step when the sign-up cannot be taken back', async () => {
    const wrapper = await mountPage()
    await signUp(wrapper)
    holders.post.mockRejectedValueOnce(apiError(409, 'booking.shift_over'))
    await byTestId(wrapper, 'btn-guest-undo').trigger('click')
    await flushPromises()
    expect(byTestId(wrapper, 'guest-signup-done').exists()).toBe(true)
  })

  it('shows the paused list instead of the form once the server says so', async () => {
    const wrapper = await mountPage()
    await byTestId(wrapper, 'btn-pick-shift-shift-1').trigger('click')
    await byTestId(wrapper, 'guest-input-name').setValue('Anna Berg')
    holders.post.mockRejectedValueOnce(apiError(409, 'shared_list.paused'))
    holders.get.mockResolvedValueOnce({ data: publicList({ status: 'paused', days: [] }) })
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(byTestId(wrapper, 'shared-list-paused').exists()).toBe(true)
  })

  it('forgets the guest when the page is left', async () => {
    const wrapper = await mountPage()
    await signUp(wrapper)
    wrapper.unmount()
    mounted.splice(mounted.indexOf(wrapper), 1)
    const store = useGuestSignupStore()
    expect(store.list).toBeNull()
    expect(store.fields.name).toBe('')
  })
})
