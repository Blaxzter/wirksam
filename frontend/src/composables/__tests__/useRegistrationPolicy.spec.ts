import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { RegistrationPolicy } from '@/client/types.gen'

const holders = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('@/client/client.gen', () => ({ client: { get: holders.get } }))

import { resetRegistrationPolicy, useRegistrationPolicy } from '@/composables/useRegistrationPolicy'

const APPROVAL: RegistrationPolicy = {
  mode: 'approval',
  allowed_domains: ['gemeinde.de'],
  invite_bypass: true,
}

describe('useRegistrationPolicy', () => {
  beforeEach(() => {
    resetRegistrationPolicy()
    holders.get.mockReset()
  })

  it('loads the policy from the public endpoint', async () => {
    holders.get.mockResolvedValue({ data: APPROVAL })

    const { policy, load } = useRegistrationPolicy()
    await load()

    expect(holders.get).toHaveBeenCalledWith(
      expect.objectContaining({ url: '/auth/registration-policy' }),
    )
    expect(policy.value).toEqual(APPROVAL)
  })

  it('asks the server once, however many components want it', async () => {
    holders.get.mockResolvedValue({ data: APPROVAL })

    const first = useRegistrationPolicy()
    const second = useRegistrationPolicy()
    await Promise.all([first.load(), second.load()])
    await first.load()

    expect(holders.get).toHaveBeenCalledTimes(1)
    expect(second.policy.value).toEqual(APPROVAL)
  })

  it('stays null when the request fails, and tries again next time', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    holders.get.mockRejectedValueOnce(new Error('offline'))

    const { policy, load } = useRegistrationPolicy()
    expect(await load()).toBeNull()
    expect(policy.value).toBeNull()

    holders.get.mockResolvedValueOnce({ data: APPROVAL })
    expect(await load()).toEqual(APPROVAL)
  })
})
