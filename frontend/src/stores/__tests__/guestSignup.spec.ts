// @vitest-environment jsdom
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useGuestSignupStore } from '@/stores/guestSignup'

import type {
  GuestSignupManage,
  PublicSharedList,
  PublicShift,
  PublicSignupResult,
} from '@/client/types.gen'
import { PassSourceGone } from '@/lib/vouchers'
import i18n from '@/locales/i18n'

/**
 * The guest pages' store: the public list and its sign-up chain, and the
 * manage page behind a guest's link. Only the client is stubbed; the error
 * normalisation and the messages are the real ones, since what a guest reads
 * after a refusal is the point of most of these cases.
 */

const holders = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  toastApiError: vi.fn(),
}))

vi.mock('@/client/client.gen', () => ({ client: { get: holders.get, post: holders.post } }))
vi.mock('@/lib/api-errors', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api-errors')>()),
  toastApiError: holders.toastApiError,
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
      timezone: 'Europe/Berlin',
    },
    ask_email: 'optional',
    ask_phone: 'optional',
    show_names: 'none',
    max_per_person: null,
    days: [{ date: '2026-11-20', shifts: [shift(), shift({ id: 'shift-2' })] }],
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
    email: 'anna@example.org',
    mail_queued: true,
    show_manage_link: false,
    remaining: null,
    ...overrides,
  }
}

function manageView(overrides: Partial<GuestSignupManage> = {}): GuestSignupManage {
  return {
    name: 'Anna Berg',
    email: 'anna@example.org',
    event: publicList().event,
    bookings: [],
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

/** What the generated axios client throws for an answer that is not 2xx. */
function apiError(status: number, code?: string, errors?: unknown[]) {
  return { isAxiosError: true, response: { status, data: { status, code, errors } } }
}

const lastPost = () => holders.post.mock.calls.at(-1)![0]

async function loadedStore(list = publicList()) {
  const store = useGuestSignupStore()
  holders.get.mockResolvedValueOnce({ data: list })
  await store.load(list.code)
  return store
}

beforeEach(() => {
  setActivePinia(createPinia())
  i18n.global.locale.value = 'en'
  holders.get.mockReset()
  holders.post.mockReset()
  holders.toastApiError.mockReset()
})

describe('load', () => {
  it('fetches the list by its code, anonymously', async () => {
    const store = await loadedStore(publicList({ code: 'a/b' }))
    expect(holders.get).toHaveBeenCalledWith({
      url: '/public/shared-lists/a%2Fb',
      throwOnError: true,
    })
    expect(store.listState).toBe('ready')
    expect(store.list?.title).toBe('Helpers wanted')
  })

  it('shows a link that leads nowhere as missing, and anything else as failed', async () => {
    const store = useGuestSignupStore()
    holders.get.mockRejectedValueOnce(apiError(404, 'shared_list.not_found'))
    await store.load('gone')
    expect(store.listState).toBe('missing')

    holders.get.mockRejectedValueOnce(apiError(500))
    await store.load('other')
    expect(store.listState).toBe('failed')
  })

  it('keeps the list on screen when a quiet refresh fails', async () => {
    const store = await loadedStore()
    holders.get.mockRejectedValueOnce(apiError(500))
    await store.load('abc123', { silent: true })
    expect(store.listState).toBe('ready')
    expect(store.list).not.toBeNull()
  })

  it('forgets what was typed on another list', async () => {
    const store = await loadedStore()
    store.fields.name = 'Anna'
    holders.get.mockResolvedValueOnce({ data: publicList({ code: 'other' }) })
    await store.load('other')
    expect(store.fields.name).toBe('')
  })

  it('drops an answer for a list the page has already left', async () => {
    const store = useGuestSignupStore()
    let answer: (value: unknown) => void = () => {}
    holders.get.mockReturnValueOnce(new Promise((resolve) => (answer = resolve)))
    const first = store.load('first')
    holders.get.mockResolvedValueOnce({ data: publicList({ code: 'second', title: 'Second' }) })
    await store.load('second')
    answer({ data: publicList({ code: 'first', title: 'First' }) })
    await first
    expect(store.list?.title).toBe('Second')
  })

  it('drops a refusal for a list the page has already left', async () => {
    const store = useGuestSignupStore()
    let refuse: (reason: unknown) => void = () => {}
    holders.get.mockReturnValueOnce(new Promise((_, reject) => (refuse = reject)))
    const first = store.load('first')
    holders.get.mockResolvedValueOnce({ data: publicList({ code: 'second' }) })
    await store.load('second')
    refuse(apiError(404))
    await first
    expect(store.listState).toBe('ready')
  })
})

describe('signUp', () => {
  const input = { shiftId: 'shift-1', showNames: 'none' as const, turnstileToken: null }

  it('sends what was typed, trimmed, with the language and what the form showed', async () => {
    const store = await loadedStore()
    Object.assign(store.fields, {
      name: ' Anna Berg ',
      email: ' anna@example.org ',
      phone: '',
      remind: true,
    })
    i18n.global.locale.value = 'de'
    holders.post.mockResolvedValueOnce({ data: signupResult() })

    const outcome = await store.signUp({ ...input, showNames: 'first' })

    expect(outcome.ok).toBe(true)
    expect(lastPost()).toEqual({
      url: '/public/shared-lists/abc123/signups',
      body: {
        shift_id: 'shift-1',
        name: 'Anna Berg',
        email: 'anna@example.org',
        phone: null,
        remind: true,
        language: 'de',
        show_names: 'first',
      },
      throwOnError: true,
    })
  })

  it('sends the Turnstile token only when there is one', async () => {
    const store = await loadedStore()
    store.fields.name = 'Anna'
    holders.post.mockResolvedValue({ data: signupResult() })
    await store.signUp(input)
    expect(lastPost().body).not.toHaveProperty('turnstile_token')
    await store.signUp({ ...input, turnstileToken: 'solved' })
    expect(lastPost().body.turnstile_token).toBe('solved')
  })

  it('asks for no reminder without an address, and sends nothing the list does not ask for', async () => {
    const store = await loadedStore(publicList({ ask_email: 'off', ask_phone: 'off' }))
    Object.assign(store.fields, { name: 'Anna', email: 'typed@example.org', phone: '0170 1' })
    holders.post.mockResolvedValueOnce({ data: signupResult({ email: null }) })
    await store.signUp(input)
    expect(lastPost().body).toMatchObject({ email: null, phone: null, remind: false })
  })

  it('starts a chain the first time and continues it after that', async () => {
    const store = await loadedStore()
    store.fields.name = 'Anna'
    holders.post.mockResolvedValueOnce({ data: signupResult() })
    await store.signUp(input)
    expect(store.mailedTo).toBe('anna@example.org')
    expect(store.linkToKeep).toBeNull()

    holders.post.mockResolvedValueOnce({
      data: signupResult({ booking_id: 'booking-2', mail_queued: false }),
    })
    await store.signUp({ ...input, shiftId: 'shift-2' })
    expect(lastPost().body.guest_token).toBe('guest-token')
    expect(store.last?.booking_id).toBe('booking-2')
    expect(store.mailedTo).toBe('anna@example.org')
  })

  it('goes on with the new chain the server started after the old one was confirmed', async () => {
    // The guest pressed "Ja, das bin ich" in the mail's tab, which retired
    // the token this tab still sends.
    const store = await loadedStore()
    store.fields.name = 'Anna'
    holders.post.mockResolvedValueOnce({ data: signupResult() })
    await store.signUp(input)

    holders.post.mockResolvedValueOnce({
      data: signupResult({
        booking_id: 'booking-2',
        guest_token: 'new-chain',
        email: 'anna@example.net',
      }),
    })
    await store.signUp({ ...input, shiftId: 'shift-2' })
    expect(lastPost().body.guest_token).toBe('guest-token')
    expect(store.mailedTo).toBe('anna@example.net')

    holders.post.mockResolvedValueOnce({
      data: signupResult({ booking_id: 'booking-3', guest_token: 'new-chain', mail_queued: false }),
    })
    await store.signUp(input)
    expect(lastPost().body.guest_token).toBe('new-chain')
    expect(store.mailedTo).toBe('anna@example.net')
  })

  it('keeps the manage link on show when no mail went out', async () => {
    const store = await loadedStore()
    store.fields.name = 'Anna'
    holders.post.mockResolvedValueOnce({
      data: signupResult({ email: null, mail_queued: false, show_manage_link: true }),
    })
    await store.signUp(input)
    expect(store.linkToKeep).toBe('guest-token')
    expect(store.mailedTo).toBeNull()
  })

  it('takes the shift as the answer counts it, without fetching the list again', async () => {
    const store = await loadedStore()
    store.fields.name = 'Anna'
    holders.post.mockResolvedValueOnce({
      data: signupResult({ shift: shift({ free: 0, full: true }) }),
    })
    await store.signUp(input)
    expect(store.list?.days[0]!.shifts[0]).toMatchObject({ free: 0, full: true })
    expect(store.list?.days[0]!.shifts[1]!.free).toBe(2)
    expect(holders.get).toHaveBeenCalledTimes(1)
  })

  it('says a shift has just filled up, and fetches the list again', async () => {
    const store = await loadedStore()
    store.fields.name = 'Anna'
    holders.post.mockRejectedValueOnce(apiError(409, 'booking.slot_full'))
    holders.get.mockResolvedValueOnce({ data: publicList() })
    const outcome = await store.signUp(input)
    expect(outcome).toEqual({
      ok: false,
      message: 'This shift has just filled up. Please pick another one.',
    })
    expect(holders.get).toHaveBeenCalledTimes(2)
  })

  it('names the limit per person when the list has one', async () => {
    const store = await loadedStore(publicList({ max_per_person: 2 }))
    store.fields.name = 'Anna'
    holders.post.mockRejectedValueOnce(apiError(409, 'shared_list.max_per_person'))
    const outcome = await store.signUp(input)
    expect(outcome).toMatchObject({
      message: 'Through this list, one person can sign up for at most 2 shifts.',
    })
  })

  it('falls back to the general message about the limit when the list shows none', async () => {
    const store = await loadedStore()
    store.fields.name = 'Anna'
    holders.post.mockRejectedValueOnce(apiError(409, 'shared_list.max_per_person'))
    const outcome = await store.signUp(input)
    expect(outcome).toMatchObject({
      message: 'You have signed up for as many shifts on this list as one person can.',
    })
  })

  it.each([
    ['shared_list.email_required', 'email', 'Please enter your email address'],
    ['shared_list.phone_required', 'phone', 'Please enter a phone number.'],
  ])('puts %s on its field', async (code, field, message) => {
    const store = await loadedStore()
    store.fields.name = 'Anna'
    holders.post.mockRejectedValueOnce(apiError(422, code))
    const outcome = await store.signUp(input)
    expect(outcome).toMatchObject({ ok: false, field })
    expect(outcome.ok === false && outcome.message).toContain(message)
  })

  it('reads a field the server refused out of its validation errors', async () => {
    const store = await loadedStore()
    store.fields.name = 'Anna'
    holders.post.mockRejectedValueOnce(
      apiError(422, undefined, [{ loc: ['body', 'email'], msg: 'bad', type: 'value_error' }]),
    )
    const outcome = await store.signUp(input)
    expect(outcome).toEqual({
      ok: false,
      field: 'email',
      message: "That email address doesn't look complete.",
    })
  })

  it('passes any other refusal on in words', async () => {
    const store = await loadedStore()
    store.fields.name = 'Anna'
    holders.post.mockRejectedValueOnce(apiError(409, 'shared_list.already_signed_up'))
    const outcome = await store.signUp(input)
    expect(outcome).toEqual({ ok: false, message: 'You are already signed up for this shift.' })
  })

  it('starts a new chain when the old one cannot be continued', async () => {
    const store = await loadedStore()
    store.fields.name = 'Anna'
    holders.post.mockResolvedValueOnce({ data: signupResult() })
    await store.signUp(input)
    holders.post.mockRejectedValueOnce(apiError(403, 'shared_list.guest_token_invalid'))
    await store.signUp(input)
    holders.post.mockResolvedValueOnce({ data: signupResult({ guest_token: 'new-token' }) })
    await store.signUp(input)
    expect(lastPost().body).not.toHaveProperty('guest_token')
  })

  it('refuses without a list to sign up on', async () => {
    const store = useGuestSignupStore()
    const outcome = await store.signUp(input)
    expect(outcome.ok).toBe(false)
    expect(holders.post).not.toHaveBeenCalled()
  })
})

describe('undo and reset', () => {
  async function signedUp() {
    const store = await loadedStore()
    Object.assign(store.fields, { name: 'Anna', email: 'anna@example.org' })
    holders.post.mockResolvedValueOnce({ data: signupResult() })
    await store.signUp({ shiftId: 'shift-1', showNames: 'none', turnstileToken: null })
    return store
  }

  it('takes back the sign-up with the token that answered it, keeping the fields', async () => {
    const store = await signedUp()
    holders.post.mockResolvedValueOnce({ data: manageView() })
    holders.get.mockResolvedValueOnce({ data: publicList() })

    expect(await store.undo()).toBe(true)

    expect(lastPost()).toEqual({
      url: '/public/guest-signups/cancel',
      body: { token: 'guest-token', booking_id: 'booking-1' },
      throwOnError: true,
    })
    expect(store.last).toBeNull()
    expect(store.fields.name).toBe('Anna')
    expect(holders.get).toHaveBeenCalledTimes(2)
  })

  it('takes back a sign-up of a new chain with that chain’s token', async () => {
    const store = await signedUp()
    holders.post.mockResolvedValueOnce({
      data: signupResult({ booking_id: 'booking-2', guest_token: 'new-chain' }),
    })
    await store.signUp({ shiftId: 'shift-2', showNames: 'none', turnstileToken: null })
    holders.post.mockResolvedValueOnce({ data: manageView() })
    holders.get.mockResolvedValueOnce({ data: publicList() })

    expect(await store.undo()).toBe(true)
    expect(lastPost().body).toEqual({ token: 'new-chain', booking_id: 'booking-2' })
  })

  it('keeps the sign-up and says why when it cannot be taken back', async () => {
    const store = await signedUp()
    const error = apiError(409, 'booking.shift_over')
    holders.post.mockRejectedValueOnce(error)
    expect(await store.undo()).toBe(false)
    expect(holders.toastApiError).toHaveBeenCalledWith(error)
    expect(store.last).not.toBeNull()
  })

  it('has nothing to undo before a sign-up', async () => {
    const store = await loadedStore()
    expect(await store.undo()).toBe(false)
    expect(holders.post).not.toHaveBeenCalled()
  })

  it('forgets the guest entirely for the next person', async () => {
    const store = await signedUp()
    holders.get.mockResolvedValueOnce({ data: publicList() })
    store.reset()
    expect(store.fields).toEqual({ name: '', email: '', phone: '', remind: true })
    expect(store.last).toBeNull()
    expect(store.mailedTo).toBeNull()
    expect(store.linkToKeep).toBeNull()
    expect(holders.get).toHaveBeenCalledTimes(2)

    holders.post.mockResolvedValueOnce({ data: signupResult() })
    store.fields.name = 'Ben'
    await store.signUp({ shiftId: 'shift-1', showNames: 'none', turnstileToken: null })
    expect(lastPost().body).not.toHaveProperty('guest_token')
  })

  it('has nothing to refresh on a page without a list', () => {
    const store = useGuestSignupStore()
    store.reset()
    expect(holders.get).not.toHaveBeenCalled()
  })
})

describe('the manage page', () => {
  async function managed(view = manageView()) {
    const store = useGuestSignupStore()
    holders.post.mockResolvedValueOnce({ data: view })
    await store.manage('manage-token')
    return store
  }

  it('reads the sign-ups with the token in the body', async () => {
    const store = await managed()
    expect(lastPost()).toEqual({
      url: '/public/guest-signups/manage',
      body: { token: 'manage-token' },
      throwOnError: true,
    })
    expect(store.manageState).toBe('ready')
    expect(store.manageView?.name).toBe('Anna Berg')
  })

  it('treats a missing token as a link that does not work, without asking', async () => {
    const store = useGuestSignupStore()
    await store.manage('')
    expect(store.manageState).toBe('missing')
    expect(holders.post).not.toHaveBeenCalled()
  })

  it('tells a dead link from a failure', async () => {
    const store = useGuestSignupStore()
    holders.post.mockRejectedValueOnce(apiError(404, 'guest_signup.not_found'))
    await store.manage('dead')
    expect(store.manageState).toBe('missing')

    holders.post.mockRejectedValueOnce(apiError(503))
    await store.manage('fine')
    expect(store.manageState).toBe('failed')
  })

  it('takes the guest off one shift and shows the page as it is now', async () => {
    const store = await managed()
    holders.post.mockResolvedValueOnce({ data: manageView({ name: 'Updated' }) })
    expect(await store.cancel('booking-1')).toBe(true)
    expect(lastPost()).toEqual({
      url: '/public/guest-signups/cancel',
      body: { token: 'manage-token', booking_id: 'booking-1' },
      throwOnError: true,
    })
    expect(store.manageView?.name).toBe('Updated')
  })

  it('switches the reminders', async () => {
    const store = await managed()
    holders.post.mockResolvedValueOnce({ data: manageView() })
    expect(await store.setReminders(false)).toBe(true)
    expect(lastPost().body).toEqual({ token: 'manage-token', enabled: false })
  })

  it('says why an action was refused and keeps the page', async () => {
    const store = await managed()
    const error = apiError(409, 'booking.shift_over')
    holders.post.mockRejectedValueOnce(error)
    expect(await store.cancel('booking-1')).toBe(false)
    expect(holders.toastApiError).toHaveBeenCalledWith(error)
    expect(store.manageState).toBe('ready')
  })

  it('shows a link that stopped working meanwhile as dead', async () => {
    const store = await managed()
    holders.post.mockRejectedValueOnce(apiError(404, 'guest_signup.not_found'))
    expect(await store.setReminders(true)).toBe(false)
    expect(store.manageState).toBe('missing')
    expect(store.manageView).toBeNull()
  })

  it('erases the guest and forgets the token', async () => {
    const store = await managed()
    holders.post.mockResolvedValueOnce({ data: '' })
    expect(await store.erase()).toBe(true)
    expect(lastPost()).toMatchObject({
      url: '/public/guest-signups/erase',
      body: { token: 'manage-token' },
    })
    expect(store.manageState).toBe('erased')
    expect(store.manageView).toBeNull()

    holders.post.mockRejectedValueOnce(apiError(404, 'guest_signup.not_found'))
    await store.notMe()
    expect(lastPost().body).toEqual({ token: null })
  })

  it('says "that was not me" from a mail link', async () => {
    const store = await managed(manageView({ can_reject: true }))
    holders.post.mockResolvedValueOnce({ data: '' })
    expect(await store.notMe()).toBe(true)
    expect(lastPost().url).toBe('/public/guest-signups/not-me')
    expect(store.manageState).toBe('rejected')
  })

  it('keeps the page when the server wants the link from the mail', async () => {
    const store = await managed()
    const error = apiError(403, 'guest_signup.mail_link_required')
    holders.post.mockRejectedValueOnce(error)
    expect(await store.notMe()).toBe(false)
    expect(holders.toastApiError).toHaveBeenCalledWith(error)
    expect(store.manageState).toBe('ready')
    expect(holders.post).toHaveBeenCalledTimes(2)
  })

  it('reads the page again when the sign-ups were confirmed before "that was not me"', async () => {
    const store = await managed(manageView({ can_confirm: true, can_reject: true }))
    const error = apiError(409, 'guest_signup.reject_confirmed')
    holders.post
      .mockRejectedValueOnce(error)
      .mockResolvedValueOnce({ data: manageView({ confirmed: true, name: 'Maria Muster' }) })

    expect(await store.notMe()).toBe(false)

    expect(holders.toastApiError).toHaveBeenCalledWith(error)
    expect(lastPost()).toEqual({
      url: '/public/guest-signups/manage',
      body: { token: 'manage-token' },
      throwOnError: true,
    })
    expect(store.manageView).toMatchObject({ confirmed: true, name: 'Maria Muster' })
    expect(store.manageState).toBe('ready')
  })
})

describe('confirming the address', () => {
  async function managed(view = manageView({ can_confirm: true, can_reject: true })) {
    const store = useGuestSignupStore()
    holders.post.mockResolvedValueOnce({ data: view })
    await store.manage('mail-token')
    return store
  }

  it('confirms with the token, then goes on with the one the answer carries', async () => {
    const store = await managed()
    holders.post.mockResolvedValueOnce({
      data: { token: 'account-token', manage: manageView({ confirmed: true, name: 'Pooled' }) },
    })
    expect(await store.confirm()).toBe(true)
    expect(lastPost()).toEqual({
      url: '/public/guest-signups/confirm',
      body: { token: 'mail-token' },
      throwOnError: true,
    })
    expect(store.manageView?.confirmed).toBe(true)
    expect(store.manageView?.name).toBe('Pooled')

    holders.post.mockResolvedValueOnce({ data: manageView({ confirmed: true }) })
    await store.setReminders(true)
    expect(lastPost().body).toEqual({ token: 'account-token', enabled: true })
  })

  it('says why a confirmation was refused and keeps the page and its token', async () => {
    const store = await managed()
    const error = apiError(403, 'guest_signup.mail_link_required')
    holders.post.mockRejectedValueOnce(error)
    expect(await store.confirm()).toBe(false)
    expect(holders.toastApiError).toHaveBeenCalledWith(error)
    expect(store.manageState).toBe('ready')

    holders.post.mockResolvedValueOnce({ data: manageView() })
    await store.setReminders(false)
    expect(lastPost().body).toEqual({ token: 'mail-token', enabled: false })
  })

  it('shows a link that died before it was confirmed as dead', async () => {
    const store = await managed()
    holders.post.mockRejectedValueOnce(apiError(404, 'guest_signup.not_found'))
    expect(await store.confirm()).toBe(false)
    expect(store.manageState).toBe('missing')
  })
})

describe('the codes a guest shows', () => {
  async function managed() {
    const store = useGuestSignupStore()
    holders.post.mockResolvedValueOnce({ data: manageView() })
    await store.manage('manage-token')
    return store
  }

  const pass = {
    id: 'pass-1',
    code: 'K7M4QX',
    qr_payload: 'WV1:K7M4QX',
    expires_at: '2026-11-20T10:02:00',
    ttl_seconds: 120,
    event_name: 'Summer fair',
  }

  it('asks for a code and its status with the token and the event', async () => {
    const store = await managed()
    const source = store.passSource('event-1')

    holders.post.mockResolvedValueOnce({ data: pass })
    expect(await source.issue()).toEqual(pass)
    expect(lastPost()).toEqual({
      url: '/public/guest-signups/vouchers/pass',
      body: { token: 'manage-token', event_id: 'event-1' },
      throwOnError: true,
    })

    holders.post.mockResolvedValueOnce({ data: { status: 'active', available: 2 } })
    expect(await source.status('pass-1')).toEqual({ status: 'active', available: 2 })
    expect(lastPost()).toEqual({
      url: '/public/guest-signups/vouchers/pass-status',
      body: { token: 'manage-token', event_id: 'event-1', pass_id: 'pass-1' },
      throwOnError: true,
    })
  })

  it('asks with the token the page holds by then, after a confirmation', async () => {
    const store = await managed()
    const source = store.passSource('event-1')
    holders.post.mockResolvedValueOnce({ data: { token: 'account-token', manage: manageView() } })
    await store.confirm()

    holders.post.mockResolvedValueOnce({ data: pass })
    await source.issue()
    expect(lastPost().body).toEqual({ token: 'account-token', event_id: 'event-1' })
  })

  it('treats a code that was replaced as an ordinary failed status', async () => {
    const store = await managed()
    const error = apiError(404, 'voucher.pass_not_found')
    holders.post.mockRejectedValueOnce(error)
    await expect(store.passSource('event-1').status('pass-1')).rejects.toBe(error)
    expect(store.manageState).toBe('ready')
  })

  it('says the link is gone once it no longer works, for a code and for its status', async () => {
    const store = await managed()
    const source = store.passSource('event-1')
    holders.post.mockRejectedValueOnce(apiError(404, 'guest_signup.not_found'))
    await expect(source.status('pass-1')).rejects.toBeInstanceOf(PassSourceGone)
    holders.post.mockRejectedValueOnce(apiError(404, 'guest_signup.not_found'))
    await expect(source.issue()).rejects.toBeInstanceOf(PassSourceGone)
    expect(source.goneMessage).toBe(i18n.global.t('guestSignup.manage.vouchers.linkGone'))
    expect(source.goneMessage).toContain('This link no longer works')
  })

  it('passes a refusal of too many codes on as it is', async () => {
    const store = await managed()
    const error = apiError(429, 'voucher.rate_limited')
    holders.post.mockRejectedValueOnce(error)
    await expect(store.passSource('event-1').issue()).rejects.toBe(error)
  })

  it('asks nothing once the page has let go of its token', async () => {
    const store = await managed()
    const source = store.passSource('event-1')
    store.clear()
    holders.post.mockClear()
    await expect(source.issue()).rejects.toBeInstanceOf(PassSourceGone)
    expect(holders.post).not.toHaveBeenCalled()
  })

  it('says what is gone in the language the page is in when it says it', async () => {
    const store = await managed()
    const source = store.passSource('event-1')
    i18n.global.locale.value = 'de'
    expect(source.goneMessage).toContain('Dieser Link funktioniert nicht mehr')
  })
})

describe('reloading the manage page', () => {
  it('shows the page as it is now, e.g. after a redemption', async () => {
    const store = useGuestSignupStore()
    holders.post.mockResolvedValueOnce({ data: manageView() })
    await store.manage('manage-token')

    holders.post.mockResolvedValueOnce({ data: manageView({ name: 'Fresh' }) })
    await store.reloadManage()
    expect(lastPost()).toMatchObject({ url: '/public/guest-signups/manage' })
    expect(store.manageView?.name).toBe('Fresh')
  })

  it('keeps what is on screen after a passing failure, and ends a dead link', async () => {
    const store = useGuestSignupStore()
    holders.post.mockResolvedValueOnce({ data: manageView() })
    await store.manage('manage-token')

    holders.post.mockRejectedValueOnce(apiError(503))
    await store.reloadManage()
    expect(store.manageState).toBe('ready')
    expect(store.manageView?.name).toBe('Anna Berg')
    expect(holders.toastApiError).not.toHaveBeenCalled()

    holders.post.mockRejectedValueOnce(apiError(404, 'guest_signup.not_found'))
    await store.reloadManage()
    expect(store.manageState).toBe('missing')
  })

  it('asks nothing without a link', async () => {
    const store = useGuestSignupStore()
    await store.reloadManage()
    expect(holders.post).not.toHaveBeenCalled()
  })
})

describe('clear', () => {
  it('leaves nothing of the guest behind', async () => {
    const store = await loadedStore()
    store.fields.name = 'Anna'
    holders.post.mockResolvedValueOnce({ data: signupResult() })
    await store.signUp({ shiftId: 'shift-1', showNames: 'none', turnstileToken: null })
    holders.post.mockResolvedValueOnce({ data: manageView() })
    await store.manage('manage-token')

    store.clear()

    expect(store.list).toBeNull()
    expect(store.listState).toBe('idle')
    expect(store.fields.name).toBe('')
    expect(store.last).toBeNull()
    expect(store.manageView).toBeNull()
    expect(store.manageState).toBe('idle')
  })
})
