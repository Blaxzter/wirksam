// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import VoucherRedeemConfirm, {
  type RedeemSubject,
} from '@/components/vouchers/VoucherRedeemConfirm.vue'

import i18n from '@/locales/i18n'

/**
 * The redeem sheet: who is at the counter as a chip with what they have, how
 * many to take, then a big "1 voucher redeemed" with what is left. "Next
 * person" tells the page once the sheet has gone (so the page can focus the
 * code field or reopen the picker without the closing sheet taking focus
 * back); "Done" only closes it.
 */

const api = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ post: api.post }),
}))

const toastApiError = vi.fn((_error: unknown) => ({ code: null }))
vi.mock('@/lib/api-errors', () => ({ toastApiError: (e: unknown) => toastApiError(e) }))

const isPhone = ref(true)
vi.mock('@vueuse/core', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@vueuse/core')>()),
  useMediaQuery: () => isPhone,
}))

const passthrough = { template: '<div><slot /></div>' }
// Stays rendered when closed, as the real sheet does while it animates out:
// that is when it hands focus back.
const dialogStub = {
  props: ['open'],
  template: '<div data-stub="dialog" :data-open="open"><slot /></div>',
}
/** Stands in for the sheet; `close-focus` plays the moment it hands focus back. */
const contentStub = {
  emits: ['closeAutoFocus'],
  methods: {
    fireClose(this: { $emit: (e: string, v: Event) => void }) {
      const event = new Event('focus', { cancelable: true })
      this.$emit('closeAutoFocus', event)
      return event
    },
  },
  template: '<div><slot /></div>',
}

const VRONI: RedeemSubject = {
  code: 'K7M4QX',
  userId: 'u-vroni',
  name: 'Vroni Hartmann',
  avatarEtag: null,
  available: 2,
}

async function openSheet(subject: RedeemSubject = VRONI) {
  const w = mount(VoucherRedeemConfirm, {
    props: { open: false, eventId: 'e1', taskId: 't1', subject },
    global: {
      plugins: [i18n],
      stubs: {
        ResponsiveDialog: dialogStub,
        ResponsiveDialogContent: contentStub,
        ResponsiveDialogHeader: passthrough,
        ResponsiveDialogTitle: passthrough,
        ResponsiveDialogDescription: passthrough,
        ResponsiveDialogBody: passthrough,
        ResponsiveDialogFooter: passthrough,
      },
    },
  })
  await w.setProps({ open: true })
  return w
}

type Wrapper = Awaited<ReturnType<typeof openSheet>>

const byId = (w: Wrapper, id: string) => w.find(`[data-testid="${id}"]`)
const flush = () => new Promise((r) => setTimeout(r, 0))

function answer(available: number, amount = 1) {
  api.post.mockResolvedValueOnce({
    data: {
      entry: { id: 'r1', kind: 'redemption', amount: -amount, created_at: '2026-07-17T21:30:00' },
      name: 'Vroni Hartmann',
      available,
      replayed: false,
    },
  })
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
  isPhone.value = true
  api.post.mockReset()
  toastApiError.mockClear()
})

describe('VoucherRedeemConfirm', () => {
  it('shows the person with what they have and offers to redeem one', async () => {
    const w = await openSheet()
    expect(byId(w, 'voucher-redeem-person').text()).toContain('Vroni Hartmann')
    expect(byId(w, 'voucher-redeem-available').text()).toBe('2 available')
    expect(byId(w, 'voucher-redeem-available').classes()).toContain('bg-hero-chip')
    expect(byId(w, 'btn-voucher-redeem').text()).toBe('Redeem 1 voucher')
  })

  it('redeems with the code, then says how many, for whom and what is left', async () => {
    const w = await openSheet()
    answer(1)
    await byId(w, 'btn-voucher-redeem').trigger('click')
    await flush()

    expect(api.post).toHaveBeenCalledWith({
      url: '/events/e1/vouchers/redeem',
      body: expect.objectContaining({ task_id: 't1', code: 'K7M4QX', amount: 1 }),
    })
    expect(byId(w, 'voucher-redeem-success').text()).toContain('1 voucher redeemed')
    expect(byId(w, 'voucher-redeem-success').text()).toContain('for Vroni Hartmann')
    expect(byId(w, 'voucher-redeem-left').text()).toBe('1 left')
    expect(w.emitted('redeemed')).toHaveLength(1)
    // The amount step is gone; "Done" and "Next person" are left.
    expect(byId(w, 'btn-voucher-redeem').exists()).toBe(false)
    expect(byId(w, 'btn-voucher-done').text()).toBe('Done')
    expect(byId(w, 'btn-voucher-next').text()).toBe('Next person')
  })

  it('says "none left" once the last one is taken', async () => {
    const w = await openSheet({ ...VRONI, available: 1 })
    answer(0)
    await byId(w, 'btn-voucher-redeem').trigger('click')
    await flush()
    expect(byId(w, 'voucher-redeem-left').text()).toBe('none left')
  })

  it('redeems by person when they were picked by hand, and offers the picker next', async () => {
    const w = await openSheet({ ...VRONI, code: null })
    answer(1)
    await byId(w, 'btn-voucher-redeem').trigger('click')
    await flush()

    expect(api.post.mock.calls[0]![0].body).toMatchObject({ user_id: 'u-vroni' })
    expect(api.post.mock.calls[0]![0].body).not.toHaveProperty('code')
    expect(byId(w, 'btn-voucher-next').find('.lucide-user-search').exists()).toBe(true)
  })

  it('offers the camera next after a code', async () => {
    const w = await openSheet()
    answer(1)
    await byId(w, 'btn-voucher-redeem').trigger('click')
    await flush()
    expect(byId(w, 'btn-voucher-next').find('.lucide-scan-line').exists()).toBe(true)
  })

  it('tells the page about "Next person" only once the sheet hands focus back', async () => {
    const w = await openSheet()
    answer(1)
    await byId(w, 'btn-voucher-redeem').trigger('click')
    await flush()

    const content = w.findComponent(contentStub)
    await byId(w, 'btn-voucher-next').trigger('click')
    expect(w.emitted('update:open')?.at(-1)).toEqual([false])
    expect(w.emitted('next')).toBeUndefined()

    const event = (content.vm as unknown as { fireClose: () => Event }).fireClose()
    expect(w.emitted('next')).toHaveLength(1)
    // The page decides where focus goes, not the closing sheet.
    expect(event.defaultPrevented).toBe(true)
  })

  it('only closes on "Done"', async () => {
    const w = await openSheet()
    answer(1)
    await byId(w, 'btn-voucher-redeem').trigger('click')
    await flush()

    const content = w.findComponent(contentStub)
    await byId(w, 'btn-voucher-done').trigger('click')
    expect(w.emitted('update:open')?.at(-1)).toEqual([false])
    const event = (content.vm as unknown as { fireClose: () => Event }).fireClose()
    expect(w.emitted('next')).toBeUndefined()
    expect(event.defaultPrevented).toBe(false)
  })

  it('has nothing to choose for someone with nothing left', async () => {
    const w = await openSheet({ ...VRONI, available: 0 })
    expect(w.text()).toContain('Vroni Hartmann has no vouchers left to redeem.')
    expect(byId(w, 'voucher-redeem-available').text()).toBe('0 available')
    expect(byId(w, 'voucher-redeem-available').classes()).toContain('bg-secondary')
    expect(byId(w, 'voucher-redeem-amount').exists()).toBe(false)
    expect(byId(w, 'btn-voucher-redeem').exists()).toBe(false)
    expect(byId(w, 'btn-voucher-next').exists()).toBe(true)
  })

  it('reads in German with the artboard copy', async () => {
    i18n.global.locale.value = 'de'
    const w = await openSheet()
    expect(byId(w, 'voucher-redeem-available').text()).toBe('2 verfügbar')
    expect(byId(w, 'btn-voucher-redeem').text()).toBe('1 Marke einlösen')
    answer(1)
    await byId(w, 'btn-voucher-redeem').trigger('click')
    await flush()
    expect(byId(w, 'voucher-redeem-success').text()).toContain('1 Marke eingelöst')
    expect(byId(w, 'voucher-redeem-success').text()).toContain('für Vroni Hartmann')
    expect(byId(w, 'voucher-redeem-left').text()).toBe('noch 1 übrig')
    expect(byId(w, 'btn-voucher-done').text()).toBe('Fertig')
    expect(byId(w, 'btn-voucher-next').text()).toBe('Nächste Person')
  })

  it('gives "Cancel" a plain look on a phone and an outline on a wider screen', async () => {
    const cancel = (w: Wrapper) => w.findAll('button').find((b) => b.text() === 'Cancel')!
    const phone = await openSheet()
    expect(cancel(phone).classes()).not.toContain('border')
    expect(byId(phone, 'btn-voucher-redeem').classes()).toContain('h-[54px]')

    isPhone.value = false
    const desktop = await openSheet()
    expect(cancel(desktop).classes()).toContain('border')
    expect(byId(desktop, 'btn-voucher-redeem').classes()).toContain('h-11')
  })
})
