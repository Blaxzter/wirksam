// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import EventMembers from '@/components/events/EventMembers.vue'

import type { EventMemberRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * Leaving, removing someone and handing the event over can't be taken back, and
 * the first two also cancel bookings, so each of them asks first.
 */

const api = vi.hoisted(() => ({ patch: vi.fn(), delete: vi.fn(), post: vi.fn() }))
const dialog = vi.hoisted(() => ({ confirm: vi.fn(), confirmDestructive: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({ useAuthenticatedClient: () => api }))
vi.mock('@/composables/useDialog', () => ({ useDialog: () => dialog }))
vi.mock('@/composables/useAvatarUrl', () => ({ avatarUrlFor: () => null }))
vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/lib/api-errors', () => ({ toastApiError: vi.fn() }))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ profile: { id: 'me' } }),
}))

function member(user_id: string, name: string, role: EventMemberRead['role']): EventMemberRead {
  return { user_id, name, email: `${user_id}@example.org`, role } as EventMemberRead
}

const MEMBERS = [member('me', 'Mira', 'member'), member('u2', 'Tomas', 'member')]

function mountMembers(props: Partial<InstanceType<typeof EventMembers>['$props']> = {}) {
  return mount(EventMembers, {
    props: { eventId: 'e1', members: MEMBERS, canEdit: true, ...props },
    global: { plugins: [i18n] },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('EventMembers', () => {
  it('asks before leaving, and says that bookings are cancelled', async () => {
    dialog.confirmDestructive.mockResolvedValue(false)
    const w = mountMembers()
    await w.get('[data-testid="btn-leave-event"]').trigger('click')
    await flushPromises()

    expect(dialog.confirmDestructive.mock.calls[0][0].text).toContain('bookings')
    expect(api.delete).not.toHaveBeenCalled()
  })

  it('leaves once confirmed', async () => {
    dialog.confirmDestructive.mockResolvedValue(true)
    api.delete.mockResolvedValue({})
    const w = mountMembers()
    await w.get('[data-testid="btn-leave-event"]').trigger('click')
    await flushPromises()

    expect(api.delete).toHaveBeenCalledWith({ url: '/events/e1/members/me' })
    expect(w.emitted('left')).toHaveLength(1)
  })

  it('names the person when asking before removing them', async () => {
    dialog.confirmDestructive.mockResolvedValue(false)
    const w = mountMembers()
    await w.get('[data-testid="btn-remove-member"]').trigger('click')
    await flushPromises()

    expect(dialog.confirmDestructive.mock.calls[0][0].title).toContain('Tomas')
    expect(api.delete).not.toHaveBeenCalled()
  })

  it('removes someone once confirmed', async () => {
    dialog.confirmDestructive.mockResolvedValue(true)
    api.delete.mockResolvedValue({})
    const w = mountMembers()
    await w.get('[data-testid="btn-remove-member"]').trigger('click')
    await flushPromises()

    expect(api.delete).toHaveBeenCalledWith({ url: '/events/e1/members/u2' })
    expect(w.emitted('updated')).toHaveLength(1)
  })

  it('asks before handing the event over, and hands it over once confirmed', async () => {
    dialog.confirm.mockResolvedValueOnce(false).mockResolvedValueOnce(true)
    api.post.mockResolvedValue({})
    const w = mountMembers({
      isOwner: true,
      members: [member('me', 'Mira', 'owner'), member('u2', 'Tomas', 'member')],
    })
    await w.get('[data-testid="transfer-ownership"] select').setValue('u2')

    await w.get('[data-testid="btn-transfer-ownership"]').trigger('click')
    await flushPromises()
    expect(dialog.confirm.mock.calls[0][0].title).toContain('Tomas')
    expect(api.post).not.toHaveBeenCalled()

    await w.get('[data-testid="btn-transfer-ownership"]').trigger('click')
    await flushPromises()
    expect(api.post).toHaveBeenCalledWith({
      url: '/events/e1/transfer-ownership',
      body: { new_owner_id: 'u2' },
    })
  })
})
