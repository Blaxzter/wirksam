import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

/**
 * Which writes refetch the sidebar: those that change its tasks, bookings or
 * open-shift counts, and none of the vouchers' or shared lists' own, with one
 * exception: taking people off a list frees their places.
 */

const refresh = vi.hoisted(() => vi.fn())
vi.mock('@/stores/sidebar', () => ({ useSidebarStore: () => ({ refresh }) }))

vi.mock('@/lib/auth-session', () => ({
  authSession: { getAccessToken: async () => 'token' },
}))

const send = vi.hoisted(() => vi.fn(async () => ({ data: null })))
vi.mock('@/client/client.gen', () => ({
  client: { get: send, post: send, put: send, delete: send, patch: send },
}))

beforeEach(() => {
  refresh.mockClear()
  send.mockClear()
})

describe('useAuthenticatedClient: the sidebar', () => {
  it.each([
    ['/bookings/'],
    ['/tasks/t1'],
    ['/shifts/s1'],
    ['/events/e1'],
    ['/shared-lists/l1/signups/remove'],
  ])('refetches after a write to %s', async (url) => {
    await useAuthenticatedClient().post({ url })
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it.each([
    ['/events/e1/vouchers/redeem'],
    ['/events/e1/shared-lists'],
    ['/events/e1/shared-lists/bulk'],
    ['/shared-lists/l1/pause'],
    ['/users/me'],
  ])('leaves it alone after a write to %s', async (url) => {
    await useAuthenticatedClient().post({ url })
    expect(refresh).not.toHaveBeenCalled()
  })

  it('leaves it alone after a read', async () => {
    await useAuthenticatedClient().get({ url: '/bookings/' })
    expect(refresh).not.toHaveBeenCalled()
  })

  it('sends the bearer token with every request', async () => {
    await useAuthenticatedClient().patch({ url: '/events/e1' })
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        url: '/events/e1',
        security: [expect.objectContaining({ scheme: 'bearer' })],
      }),
    )
  })
})
