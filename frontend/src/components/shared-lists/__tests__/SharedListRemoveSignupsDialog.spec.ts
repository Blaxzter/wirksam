// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useSharedListsStore } from '@/stores/sharedLists'

import SharedListRemoveSignupsDialog, {
  type RemoveTarget,
} from '@/components/shared-lists/SharedListRemoveSignupsDialog.vue'

import type { SharedListSignupRemoveResult } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * Taking people off a list. Telling them by email is on unless the organiser
 * turns it off (spam); deleting their data is only offered to event admins;
 * "this and every newer one" sends the moment, not a list of bookings.
 */

const toast = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), info: vi.fn() }))
const toastApiError = vi.hoisted(() => vi.fn())
vi.mock('vue-sonner', () => ({ toast }))
vi.mock('@/lib/api-errors', () => ({ toastApiError }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: { time_format: 'h24' } }) }))
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }),
}))

const passthrough = { template: '<div><slot /></div>' }
const Content = defineComponent({
  name: 'ResponsiveDialogContent',
  emits: ['closeAutoFocus'],
  template: '<div><slot /></div>',
})

function mountDialog(target: RemoveTarget, canErase: boolean) {
  return mount(SharedListRemoveSignupsDialog, {
    props: { listId: 'l1', target, canErase, open: true },
    global: {
      plugins: [i18n],
      stubs: {
        ResponsiveDialog: passthrough,
        ResponsiveDialogContent: Content,
        ResponsiveDialogHeader: passthrough,
        ResponsiveDialogTitle: passthrough,
        ResponsiveDialogDescription: passthrough,
        ResponsiveDialogBody: passthrough,
        ResponsiveDialogFooter: passthrough,
      },
    },
  })
}

const ONE: RemoveTarget = {
  kind: 'bookings',
  bookingIds: ['b1'],
  one: { name: 'Mia Berger', task: 'Kuchen', when: 'Thu, Nov 19, 18:00 – 20:00' },
  pooled: 0,
}

/** The dialog has played its closing animation and would hand focus back. */
function closeAutoFocus(w: ReturnType<typeof mountDialog>): Event {
  const event = new Event('focus.autoFocusOnUnmount', { cancelable: true })
  w.findComponent(Content).vm.$emit('closeAutoFocus', event)
  return event
}

function spyRemove(
  result: SharedListSignupRemoveResult = {
    removed: ['b1'],
    erased_guests: 0,
    also_removed: 0,
    skipped: [],
  },
) {
  return vi.spyOn(useSharedListsStore(), 'removeSignups').mockResolvedValue(result)
}

beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
  i18n.global.locale.value = 'en'
})

describe('SharedListRemoveSignupsDialog', () => {
  it('names the one sign-up and tells them by email unless asked not to', async () => {
    const remove = spyRemove()
    const w = mountDialog(ONE, false)

    // The task and the shift, not just the person, who may be down for several.
    expect(w.text()).toContain('Remove “Mia Berger” from “Kuchen”?')
    expect(w.text()).toContain('The place on Thu, Nov 19, 18:00 – 20:00 becomes free again.')
    expect(w.get('[data-testid="shared-list-remove-notify"]').attributes('aria-checked')).toBe(
      'true',
    )
    await w.get('[data-testid="shared-list-remove-confirm"]').trigger('click')
    await flushPromises()

    expect(remove).toHaveBeenCalledWith('l1', { booking_ids: ['b1'], notify: true, erase: false })
    expect(toast.success).toHaveBeenCalledWith('1 sign-up removed.')
    expect(w.emitted('done')).toHaveLength(1)
    expect(w.emitted('update:open')).toEqual([[false]])
  })

  it('offers to delete the data to event admins only', () => {
    expect(mountDialog(ONE, false).find('[data-testid="shared-list-remove-erase"]').exists()).toBe(
      false,
    )
    expect(mountDialog(ONE, true).find('[data-testid="shared-list-remove-erase"]').exists()).toBe(
      true,
    )
  })

  it('says that deleting the data lets unredeemed vouchers expire', () => {
    expect(
      mountDialog(ONE, true).find('[data-testid="shared-list-remove-erase-hint"]').text(),
    ).toContain('Unredeemed vouchers expire with it.')
  })

  it('removes the ticked sign-ups quietly and deletes the data when asked', async () => {
    const remove = spyRemove({
      removed: ['b1', 'b2'],
      erased_guests: 2,
      also_removed: 0,
      skipped: [],
    })
    const w = mountDialog({ kind: 'bookings', bookingIds: ['b1', 'b2'], pooled: 0 }, true)

    expect(w.text()).toContain('Remove 2 sign-ups?')
    expect(w.text()).toContain('The places become free again.')
    expect(w.text()).toContain("Also delete these people's data")
    await w.get('[data-testid="shared-list-remove-notify"]').trigger('click')
    await w.get('[data-testid="shared-list-remove-erase"]').trigger('click')
    await w.get('[data-testid="shared-list-remove-confirm"]').trigger('click')
    await flushPromises()

    expect(remove).toHaveBeenCalledWith('l1', {
      booking_ids: ['b1', 'b2'],
      notify: false,
      erase: true,
    })
    expect(toast.success).toHaveBeenCalledWith('2 sign-ups removed.')
    expect(toast.success).toHaveBeenCalledWith('The data of 2 people is deleted.')
  })

  it('says which other sign-ups a confirmed address takes along, and counts them', async () => {
    // Yvonne confirmed into the account Xaver's sign-up is pooled in.
    const remove = spyRemove({ removed: ['b1'], erased_guests: 1, also_removed: 1, skipped: [] })
    const w = mountDialog({ ...ONE, pooled: 1 }, true)

    expect(w.get('[data-testid="shared-list-remove-erase-pooled"]').text()).toBe(
      "1 more sign-up is confirmed under the same email address, maybe someone else's. It is deleted too.",
    )
    await w.get('[data-testid="shared-list-remove-erase"]').trigger('click')
    await w.get('[data-testid="shared-list-remove-confirm"]').trigger('click')
    await flushPromises()

    expect(remove).toHaveBeenCalledWith('l1', { booking_ids: ['b1'], notify: true, erase: true })
    expect(toast.success).toHaveBeenCalledWith('2 sign-ups removed.')
  })

  it('says nothing of other sign-ups where none go along, or to whoever cannot delete', () => {
    expect(
      mountDialog(ONE, true).find('[data-testid="shared-list-remove-erase-pooled"]').exists(),
    ).toBe(false)
    expect(
      mountDialog({ ...ONE, pooled: 2 }, false)
        .find('[data-testid="shared-list-remove-erase-pooled"]')
        .exists(),
    ).toBe(false)
  })

  it('takes everything from one sign-up on by its moment', async () => {
    const remove = spyRemove({
      removed: ['b1'],
      erased_guests: 0,
      also_removed: 0,
      skipped: [{ id: 'b9', code: 'booking.shift_over' }],
    })
    const w = mountDialog({ kind: 'since', createdAt: '2026-11-10T08:00:00' }, false)

    expect(w.text()).toContain('Remove this sign-up and all newer ones?')
    expect(w.text()).toContain('Everything signed up through this link since')
    await w.get('[data-testid="shared-list-remove-confirm"]').trigger('click')
    await flushPromises()

    expect(remove).toHaveBeenCalledWith('l1', {
      created_since: '2026-11-10T08:00:00',
      notify: true,
      erase: false,
    })
    expect(toast.warning).toHaveBeenCalledWith('1 sign-up could not be removed.')
  })

  it('speaks of one place when one ticked sign-up goes', () => {
    const w = mountDialog({ kind: 'bookings', bookingIds: ['b1'], pooled: 0 }, false)
    expect(w.text()).toContain('Remove 1 sign-up?')
    expect(w.text()).toContain('The place becomes free again.')
  })

  it('asks the parent where focus goes once it has closed after a removal', async () => {
    spyRemove()
    const w = mountDialog(ONE, false)
    // Closed without removing anything: focus goes back as usual.
    expect(closeAutoFocus(w).defaultPrevented).toBe(false)

    await w.get('[data-testid="shared-list-remove-confirm"]').trigger('click')
    await flushPromises()

    const event = closeAutoFocus(w)
    expect(event.defaultPrevented).toBe(true)
    expect(w.emitted('refocus')).toHaveLength(1)
  })

  it('says when there was nothing to remove', async () => {
    spyRemove({ removed: [], erased_guests: 0, also_removed: 0, skipped: [] })
    const w = mountDialog(ONE, false)
    await w.get('[data-testid="shared-list-remove-confirm"]').trigger('click')
    await flushPromises()
    expect(toast.info).toHaveBeenCalledWith('There was nothing to remove.')
  })

  it('stays open and says why when the server refuses', async () => {
    const failure = new Error('403')
    vi.spyOn(useSharedListsStore(), 'removeSignups').mockRejectedValue(failure)
    const w = mountDialog(ONE, false)

    await w.get('[data-testid="shared-list-remove-confirm"]').trigger('click')
    await flushPromises()

    expect(toastApiError).toHaveBeenCalledWith(failure)
    expect(w.emitted('done')).toBeUndefined()
    expect(w.emitted('update:open')).toBeUndefined()
  })

  it('starts each opening with email on and deletion off again', async () => {
    const w = mountDialog(ONE, true)
    await w.get('[data-testid="shared-list-remove-notify"]').trigger('click')
    await w.get('[data-testid="shared-list-remove-erase"]').trigger('click')

    await w.setProps({ open: false })
    await w.setProps({ open: true })

    expect(w.get('[data-testid="shared-list-remove-notify"]').attributes('aria-checked')).toBe(
      'true',
    )
    expect(w.get('[data-testid="shared-list-remove-erase"]').attributes('aria-checked')).toBe(
      'false',
    )
  })
})
