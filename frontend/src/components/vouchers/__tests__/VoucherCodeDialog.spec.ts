// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { type Mock, afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import VoucherCodeDialog from '@/components/vouchers/VoucherCodeDialog.vue'

import type { VoucherPassRead, VoucherPassStatus } from '@/client/types.gen'
import { PassSourceGone, type VoucherPassSource } from '@/lib/vouchers'
import i18n from '@/locales/i18n'

/**
 * The code a volunteer shows at a stand. It asks for a code when it opens, a
 * new one five seconds before the old one runs out, and every two seconds what
 * became of it: "being redeemed", then "used", which tells the page behind it
 * that the balance changed. A guest's page hands in its own source of codes;
 * once that source says the link behind it is dead, the dialog says so and
 * never asks again.
 */

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ get: api.get, post: api.post }),
}))

const passthrough = { template: '<div><slot /></div>' }

function pass(overrides: Partial<VoucherPassRead> = {}): VoucherPassRead {
  return {
    id: 'pass-1',
    code: 'K7M4QX',
    qr_payload: 'WV1:K7M4QX',
    expires_at: '2026-11-20T10:02:00',
    ttl_seconds: 120,
    event_name: 'Summer fair',
    ...overrides,
  }
}

function status(overrides: Partial<VoucherPassStatus> = {}): VoucherPassStatus {
  return { status: 'active', redeemed_amount: null, task_name: null, available: 3, ...overrides }
}

/** A refusal as the API client throws it. */
function apiError(code: string, httpStatus = 404) {
  return {
    isAxiosError: true,
    response: { status: httpStatus, data: { status: httpStatus, code } },
  }
}

type FakeSource = {
  issue: Mock<VoucherPassSource['issue']>
  status: Mock<VoucherPassSource['status']>
  goneMessage: string
}

/** A guest's source of codes, as the guest store builds one. */
function fakeSource(overrides: Partial<FakeSource> = {}): FakeSource {
  return {
    issue: vi.fn<VoucherPassSource['issue']>().mockResolvedValue(pass()),
    status: vi.fn<VoucherPassSource['status']>().mockResolvedValue(status()),
    goneMessage: 'This link no longer works.',
    ...overrides,
  }
}

function mountDialog(props: { eventId?: string; source?: VoucherPassSource }) {
  return mount(VoucherCodeDialog, {
    props: { open: true, ...props },
    global: {
      plugins: [i18n],
      stubs: {
        ResponsiveDialog: passthrough,
        ResponsiveDialogContent: passthrough,
        ResponsiveDialogHeader: passthrough,
        ResponsiveDialogTitle: passthrough,
        ResponsiveDialogDescription: passthrough,
        ResponsiveDialogBody: passthrough,
        ResponsiveDialogFooter: passthrough,
        QrCode: true,
      },
    },
  })
}

const byTestId = (w: ReturnType<typeof mountDialog>, id: string) => w.find(`[data-testid="${id}"]`)

/** Let the timers run `ms` and every request they started answer. */
async function elapse(ms: number) {
  await vi.advanceTimersByTimeAsync(ms)
  await flushPromises()
}

beforeEach(() => {
  vi.useFakeTimers()
  i18n.global.locale.value = 'en'
  api.get.mockReset()
  api.post.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('VoucherCodeDialog with a source of its own', () => {
  it('shows the code the source issues, and never asks the member routes', async () => {
    const source = fakeSource()
    const w = mountDialog({ source })
    await flushPromises()

    expect(source.issue).toHaveBeenCalledTimes(1)
    expect(byTestId(w, 'voucher-code-text').text()).toBe('K7M-4QX')
    expect(w.text()).toContain('Your code for Summer fair')
    expect(api.post).not.toHaveBeenCalled()
    expect(api.get).not.toHaveBeenCalled()
    w.unmount()
  })

  it('asks the source about the code every two seconds', async () => {
    const source = fakeSource()
    const w = mountDialog({ source })
    await flushPromises()

    await elapse(2000)
    expect(source.status).toHaveBeenCalledWith('pass-1')
    await elapse(4000)
    expect(source.status).toHaveBeenCalledTimes(3)
    w.unmount()
  })

  it('issues the next code five seconds before this one runs out', async () => {
    const source = fakeSource()
    source.issue
      .mockResolvedValueOnce(pass())
      .mockResolvedValueOnce(pass({ id: 'pass-2', code: 'ABCDEF', qr_payload: 'WV1:ABCDEF' }))
    const w = mountDialog({ source })
    await flushPromises()

    await elapse(114_000)
    expect(source.issue).toHaveBeenCalledTimes(1)
    await elapse(1000)
    expect(source.issue).toHaveBeenCalledTimes(2)
    expect(byTestId(w, 'voucher-code-text').text()).toBe('ABC-DEF')
    // The replaced code may still be in a redeemer's hands: it is asked about too.
    await elapse(2000)
    expect(source.status.mock.calls.map(([id]) => id)).toContain('pass-1')
    expect(source.status.mock.calls.at(-1)?.[0]).toBe('pass-2')
    w.unmount()
  })

  it('says the code is being redeemed while a redeemer holds it', async () => {
    const source = fakeSource({
      status: vi
        .fn<VoucherPassSource['status']>()
        .mockResolvedValue(status({ status: 'checking' })),
    })
    const w = mountDialog({ source })
    await flushPromises()
    await elapse(2000)

    expect(byTestId(w, 'voucher-code-status').text()).toContain('Being redeemed')
    w.unmount()
  })

  it('says how many were used where, and tells the page the balance changed', async () => {
    const source = fakeSource({
      status: vi
        .fn<VoucherPassSource['status']>()
        .mockResolvedValue(
          status({ status: 'used', redeemed_amount: 2, task_name: 'Bar', available: 1 }),
        ),
    })
    const w = mountDialog({ source })
    await flushPromises()
    await elapse(2000)

    expect(byTestId(w, 'voucher-code-used').text()).toContain('2 vouchers used at Bar')
    expect(byTestId(w, 'voucher-code-left').text()).toBe('1 voucher available')
    expect(w.emitted('redeemed')).toHaveLength(1)
    // Settled: nothing is asked any more.
    const calls = source.status.mock.calls.length
    await elapse(10_000)
    expect(source.status).toHaveBeenCalledTimes(calls)
    w.unmount()
  })

  it('treats a network blip as an ordinary miss and asks again', async () => {
    const source = fakeSource({
      status: vi
        .fn<VoucherPassSource['status']>()
        .mockRejectedValueOnce(new Error('Network Error'))
        .mockResolvedValue(status()),
    })
    const w = mountDialog({ source })
    await flushPromises()
    await elapse(4000)

    expect(source.status).toHaveBeenCalledTimes(2)
    expect(source.issue).toHaveBeenCalledTimes(1)
    expect(byTestId(w, 'voucher-code-gone').exists()).toBe(false)
    expect(byTestId(w, 'voucher-code-text').exists()).toBe(true)
    w.unmount()
  })

  it('shows a new code at once when the one on screen vanished', async () => {
    // Confirming the address deleted the codes shown for the sign-up.
    const source = fakeSource({
      issue: vi
        .fn<VoucherPassSource['issue']>()
        .mockResolvedValueOnce(pass())
        .mockResolvedValue(pass({ id: 'pass-2', code: 'R8T2WZ' })),
      status: vi
        .fn<VoucherPassSource['status']>()
        .mockRejectedValueOnce(apiError('voucher.pass_not_found'))
        .mockResolvedValue(status()),
    })
    const w = mountDialog({ source })
    await flushPromises()
    await elapse(2000)

    expect(source.issue).toHaveBeenCalledTimes(2)
    expect(byTestId(w, 'voucher-code-text').text()).toBe('R8T-2WZ')
    await elapse(2000)
    expect(source.status).toHaveBeenLastCalledWith('pass-2')
    // The vanished code is not asked about again.
    expect(source.status.mock.calls.filter(([id]) => id === 'pass-1')).toHaveLength(1)
    w.unmount()
  })

  it('says the code is on another screen when it vanishes a second time', async () => {
    // Two screens of one person: each new code deletes the other's.
    const source = fakeSource({
      issue: vi
        .fn<VoucherPassSource['issue']>()
        .mockResolvedValueOnce(pass())
        .mockResolvedValueOnce(pass({ id: 'pass-2', code: 'R8T2WZ' }))
        .mockResolvedValue(pass({ id: 'pass-3', code: 'H4J6MN' })),
      status: vi
        .fn<VoucherPassSource['status']>()
        .mockRejectedValueOnce(apiError('voucher.pass_not_found'))
        .mockRejectedValueOnce(apiError('voucher.pass_not_found'))
        .mockResolvedValue(status()),
    })
    const w = mountDialog({ source })
    await flushPromises()
    await elapse(4000)

    expect(source.issue).toHaveBeenCalledTimes(2)
    expect(byTestId(w, 'voucher-code-text').exists()).toBe(false)
    // Nothing failed: the other screen took over.
    expect(byTestId(w, 'voucher-code-elsewhere').text()).toContain(
      'Your code is being shown on another screen.',
    )
    expect(w.text()).not.toContain('could not be loaded')
    expect(byTestId(w, 'btn-voucher-code-retry').text()).toBe('Show it here')
    // Nothing more is asked until the volunteer chooses to.
    const asked = source.status.mock.calls.length
    await elapse(10_000)
    expect(source.issue).toHaveBeenCalledTimes(2)
    expect(source.status).toHaveBeenCalledTimes(asked)
    expect(byTestId(w, 'voucher-code-text').exists()).toBe(false)

    await byTestId(w, 'btn-voucher-code-retry').trigger('click')
    await flushPromises()
    expect(source.issue).toHaveBeenCalledTimes(3)
    expect(byTestId(w, 'voucher-code-text').text()).toBe('H4J-6MN')
    expect(byTestId(w, 'voucher-code-elsewhere').exists()).toBe(false)
    w.unmount()
  })

  it('takes no code for vanished that its own rotation is replacing', async () => {
    // Issuing deletes the code on screen, so the status answer about it can
    // be a 404 that overtakes the new code.
    let land: (next: VoucherPassRead) => void = () => {}
    const source = fakeSource()
    source.issue
      .mockResolvedValueOnce(pass())
      .mockReturnValueOnce(new Promise((resolve) => (land = resolve)))
      .mockResolvedValue(pass({ id: 'pass-3', code: 'H4J6MN' }))
    const w = mountDialog({ source })
    await flushPromises()
    await elapse(115_000)
    expect(source.issue).toHaveBeenCalledTimes(2)

    source.status.mockRejectedValue(apiError('voucher.pass_not_found'))
    await elapse(4000)
    expect(source.status).toHaveBeenLastCalledWith('pass-1')
    expect(source.issue).toHaveBeenCalledTimes(2)
    expect(byTestId(w, 'voucher-code-text').text()).toBe('K7M-4QX')

    source.status.mockResolvedValue(status())
    land(pass({ id: 'pass-2', code: 'R8T2WZ' }))
    await flushPromises()
    expect(byTestId(w, 'voucher-code-text').text()).toBe('R8T-2WZ')
    expect(byTestId(w, 'voucher-code-renew-failed').exists()).toBe(false)

    // The one replacement of a vanished code is still there for a real one.
    source.status.mockImplementation(async (id) => {
      if (id === 'pass-2') throw apiError('voucher.pass_not_found')
      return status()
    })
    await elapse(2000)
    expect(source.issue).toHaveBeenCalledTimes(3)
    expect(byTestId(w, 'voucher-code-text').text()).toBe('H4J-6MN')
    w.unmount()
  })

  it('asks for no new code once closed, when a vanished answer comes in late', async () => {
    let answer: (error: unknown) => void = () => {}
    const source = fakeSource()
    source.status.mockReturnValueOnce(new Promise((_, reject) => (answer = reject)))
    const w = mountDialog({ source })
    await flushPromises()
    await elapse(2000)
    expect(source.status).toHaveBeenCalledTimes(1)

    await w.setProps({ open: false })
    answer(apiError('voucher.pass_not_found'))
    await flushPromises()
    expect(source.issue).toHaveBeenCalledTimes(1)
    w.unmount()
  })

  it('ends on the source’s message once its link died, and stops asking', async () => {
    const source = fakeSource({
      status: vi.fn<VoucherPassSource['status']>().mockRejectedValue(new PassSourceGone()),
    })
    const w = mountDialog({ source })
    await flushPromises()
    await elapse(2000)

    expect(byTestId(w, 'voucher-code-gone').text()).toContain('This link no longer works.')
    // No promise of a code above it.
    expect(w.text()).not.toContain('Show this at the counter')
    expect(byTestId(w, 'voucher-code-text').exists()).toBe(false)
    expect(byTestId(w, 'btn-voucher-code-retry').exists()).toBe(false)
    expect(w.emitted('gone')).toHaveLength(1)
    const asked = source.status.mock.calls.length + source.issue.mock.calls.length
    // Not even the rotation: the code it would replace is gone.
    await elapse(130_000)
    expect(source.status.mock.calls.length + source.issue.mock.calls.length).toBe(asked)

    await byTestId(w, 'btn-voucher-code-close').trigger('click')
    expect(w.emitted('update:open')?.at(-1)).toEqual([false])
    w.unmount()
  })

  it('ends there too when the first code is refused for a dead link', async () => {
    const source = fakeSource({
      issue: vi.fn<VoucherPassSource['issue']>().mockRejectedValue(new PassSourceGone()),
    })
    const w = mountDialog({ source })
    await flushPromises()
    await elapse(6000)

    expect(byTestId(w, 'voucher-code-gone').exists()).toBe(true)
    expect(source.issue).toHaveBeenCalledTimes(1)
    expect(source.status).not.toHaveBeenCalled()
    w.unmount()
  })

  it('offers to try again when a code could not be loaded for another reason', async () => {
    const source = fakeSource({
      issue: vi
        .fn<VoucherPassSource['issue']>()
        .mockRejectedValueOnce(new Error('Network Error'))
        .mockResolvedValue(pass()),
    })
    const w = mountDialog({ source })
    await flushPromises()

    expect(w.text()).toContain('Your code could not be loaded')
    await byTestId(w, 'btn-voucher-code-retry').trigger('click')
    await flushPromises()
    expect(byTestId(w, 'voucher-code-text').text()).toBe('K7M-4QX')
    w.unmount()
  })

  it('starts afresh when it opens again after the link died', async () => {
    const source = fakeSource({
      issue: vi
        .fn<VoucherPassSource['issue']>()
        .mockRejectedValueOnce(new PassSourceGone())
        .mockResolvedValue(pass()),
    })
    const w = mountDialog({ source })
    await flushPromises()
    expect(byTestId(w, 'voucher-code-gone').exists()).toBe(true)

    await w.setProps({ open: false })
    await w.setProps({ open: true })
    await flushPromises()
    expect(byTestId(w, 'voucher-code-gone').exists()).toBe(false)
    expect(byTestId(w, 'voucher-code-text').text()).toBe('K7M-4QX')
    w.unmount()
  })
})

describe('VoucherCodeDialog for a member', () => {
  it('asks the member’s own routes in the given event', async () => {
    api.post.mockResolvedValue({ data: pass() })
    api.get.mockResolvedValue({ data: status() })
    const w = mountDialog({ eventId: 'e1' })
    await flushPromises()
    await elapse(2000)

    expect(api.post).toHaveBeenCalledWith({ url: '/events/e1/vouchers/me/pass' })
    expect(api.get).toHaveBeenCalledWith({ url: '/events/e1/vouchers/me/pass/pass-1' })
    expect(byTestId(w, 'voucher-code-text').text()).toBe('K7M-4QX')
    w.unmount()
  })

  it('shows a member a new code when the one on screen vanished', async () => {
    api.post
      .mockResolvedValueOnce({ data: pass() })
      .mockResolvedValue({ data: pass({ id: 'pass-2', code: 'R8T2WZ' }) })
    api.get
      .mockRejectedValueOnce(apiError('voucher.pass_not_found'))
      .mockResolvedValue({ data: status() })
    const w = mountDialog({ eventId: 'e1' })
    await flushPromises()
    await elapse(2000)

    expect(api.post).toHaveBeenCalledTimes(2)
    expect(byTestId(w, 'voucher-code-text').text()).toBe('R8T-2WZ')
    w.unmount()
  })

  it('keeps asking after a refused status, which for a member is never final', async () => {
    api.post.mockResolvedValue({ data: pass() })
    api.get.mockRejectedValueOnce(new Error('404')).mockResolvedValue({ data: status() })
    const w = mountDialog({ eventId: 'e1' })
    await flushPromises()
    await elapse(4000)

    expect(api.get).toHaveBeenCalledTimes(2)
    expect(byTestId(w, 'voucher-code-gone').exists()).toBe(false)
    w.unmount()
  })
})
