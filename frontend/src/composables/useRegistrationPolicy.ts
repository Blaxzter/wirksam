import { readonly, ref } from 'vue'

import { client } from '@/client/client.gen'
import type { RegistrationPolicy } from '@/client/types.gen'

/**
 * Who may sign up on this deployment, from `GET /auth/registration-policy`.
 *
 * Read from the backend rather than from `window.__APP_CONFIG__` like the
 * Turnstile key and the sandbox switch: those are a single value each, but this
 * is three settings the server enforces, and two copies of them configured in
 * two places is how a form ends up promising something the server refuses.
 *
 * Fetched once per page load and shared. Until it arrives — or if it never
 * does — `policy` is `null` and callers should render the open-signup form;
 * the server still has the last word on every registration.
 */
const policy = ref<RegistrationPolicy | null>(null)
let pending: Promise<RegistrationPolicy | null> | null = null

async function load(): Promise<RegistrationPolicy | null> {
  if (policy.value) return policy.value
  pending ??= client
    .get<{ data: RegistrationPolicy }, unknown, true>({
      url: '/auth/registration-policy',
      throwOnError: true,
    })
    .then((response) => {
      policy.value = response.data
      return policy.value
    })
    .catch((error: unknown) => {
      console.error('Failed to load registration policy:', error)
      pending = null
      return null
    })
  return pending
}

export function useRegistrationPolicy() {
  void load()
  return { policy: readonly(policy), load }
}

/** Test seam: forget the cached policy. */
export function resetRegistrationPolicy(): void {
  policy.value = null
  pending = null
}
