import type { UserRead } from '@/client/types.gen'

/**
 * The one status an admin sees for an account, matching the backend's
 * `status_filter` values.
 *
 * Two independent fields feed it. `approval_status` is the registration queue
 * (only ever not "approved" on a deployment running `REGISTRATION_MODE=approval`)
 * and `is_active` is the moderation switch. An account still in the queue shows
 * as pending or rejected whatever `is_active` says, because that is the decision
 * waiting on someone; suspension only means something once it was let in.
 */
export type UserStatus = 'active' | 'pending' | 'rejected' | 'suspended'

export function userStatus(user: Pick<UserRead, 'is_active' | 'approval_status'>): UserStatus {
  if (user.approval_status === 'pending') return 'pending'
  if (user.approval_status === 'rejected') return 'rejected'
  return user.is_active ? 'active' : 'suspended'
}

export function userStatusBadgeVariant(
  status: UserStatus,
): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'active') return 'default'
  if (status === 'pending') return 'secondary'
  if (status === 'rejected') return 'outline'
  return 'destructive'
}
