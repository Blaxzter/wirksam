import { computed, ref, watch } from 'vue'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import type { VoucherAccount } from '@/client/types.gen'

/**
 * The volunteer's own voucher account in the selected event.
 *
 * Lifted out of `MyVouchersCard` so the dashboard can show the same balance in
 * its own shape without a second copy of the loading rules. Those rules: read
 * the account whenever the selected event changes, drop an answer that arrives
 * for an event that is no longer selected, and treat a failed read as "no
 * account" (the volunteer is not in that event any more), so whatever shows it
 * simply stays hidden.
 *
 * `settled` says the first answer for the current event is in, whichever way
 * it went, so a page can wait for it instead of jumping when a card appears.
 */
export function useMyVoucherAccount() {
  const { get } = useAuthenticatedClient()
  const authStore = useAuthStore()

  const account = ref<VoucherAccount | null>(null)
  const settled = ref(false)

  const eventId = computed(() => authStore.selectedEventId)

  const usesVouchers = computed(() => {
    const event = authStore.selectedEvent
    if (!event || event.id !== eventId.value) return false
    return (event.voucher_task_count ?? 0) > 0 || (event.voucher_point_count ?? 0) > 0
  })

  const visible = computed(() => {
    const a = account.value
    if (!a) return false
    const s = a.summary
    // The account itself, not only the cached counts: a voucher task enabled
    // a minute ago shows up here before the selected event is re-read.
    return s.earned > 0 || s.upcoming > 0 || a.entries.length > 0 || usesVouchers.value
  })

  const isExpired = computed(() => !!authStore.selectedEvent?.is_expired)

  const canShowCode = computed(
    () => (account.value?.summary.available ?? 0) > 0 && !isExpired.value,
  )

  /** Re-read the account; what is shown stays as it is until the answer is in. */
  async function load() {
    const id = eventId.value
    if (!id) {
      account.value = null
      settled.value = true
      return
    }
    let result: VoucherAccount | null
    try {
      const res = await get<{ data: VoucherAccount }>({ url: `/events/${id}/vouchers/me` })
      result = res.data
    } catch {
      // Not in the selected event (any more): nothing to show.
      result = null
    }
    if (eventId.value !== id) return
    account.value = result
    settled.value = true
  }

  watch(
    eventId,
    () => {
      account.value = null
      settled.value = false
      void load()
    },
    { immediate: true },
  )

  return { account, eventId, visible, canShowCode, isExpired, settled, reload: load }
}
