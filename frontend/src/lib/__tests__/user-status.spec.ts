import { describe, expect, it } from 'vitest'

import { userStatus, userStatusBadgeVariant, type UserStatus } from '@/lib/user-status'

describe('userStatus', () => {
  // Every combination of the two fields, because the point of the helper is
  // that the queue outranks the moderation switch.
  const EXPECTED: Array<[boolean, 'approved' | 'pending' | 'rejected' | undefined, UserStatus]> = [
    [true, 'approved', 'active'],
    [false, 'approved', 'suspended'],
    [true, 'pending', 'pending'],
    [false, 'pending', 'pending'],
    [true, 'rejected', 'rejected'],
    [false, 'rejected', 'rejected'],
    // Older payloads without the field are approved accounts.
    [true, undefined, 'active'],
    [false, undefined, 'suspended'],
  ]

  it.each(EXPECTED)('is_active=%s, approval_status=%s -> %s', (isActive, approval, expected) => {
    expect(userStatus({ is_active: isActive, approval_status: approval })).toBe(expected)
  })
})

describe('userStatusBadgeVariant', () => {
  it('gives every status its own variant', () => {
    const statuses: UserStatus[] = ['active', 'pending', 'rejected', 'suspended']
    const variants = statuses.map(userStatusBadgeVariant)
    expect(variants).toEqual(['default', 'secondary', 'outline', 'destructive'])
  })
})
