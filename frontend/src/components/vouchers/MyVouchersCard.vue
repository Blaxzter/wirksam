<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { ArrowRight, QrCode, Ticket } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

import VoucherBalanceSummary from '@/components/vouchers/VoucherBalanceSummary.vue'
import VoucherCodeDialog from '@/components/vouchers/VoucherCodeDialog.vue'

import type { VoucherAccount } from '@/client/types.gen'

/**
 * The volunteer's vouchers in the selected event, with the button that shows
 * their code. Like `MyHoursCard` it reads the selected event and keeps out of
 * the way: it appears once there is something to show, or once the event is
 * known to use vouchers, and stays hidden if the account cannot be read.
 */
const { t } = useI18n()
const router = useRouter()
const { get } = useAuthenticatedClient()
const authStore = useAuthStore()

const account = ref<VoucherAccount | null>(null)
const codeOpen = ref(false)

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

const canShowCode = computed(
  () => (account.value?.summary.available ?? 0) > 0 && !authStore.selectedEvent?.is_expired,
)

/** Re-read the account; the card stays as it is until the answer is in. */
async function load() {
  const id = eventId.value
  if (!id) {
    account.value = null
    return
  }
  try {
    const res = await get<{ data: VoucherAccount }>({ url: `/events/${id}/vouchers/me` })
    if (eventId.value === id) account.value = res.data
  } catch {
    // Not in the selected event (any more): the card simply stays hidden.
    if (eventId.value === id) account.value = null
  }
}

watch(eventId, () => {
  account.value = null
  void load()
})
onMounted(load)

defineExpose({ reload: load })
</script>

<template>
  <Card v-if="visible && account" data-testid="my-vouchers-card">
    <CardHeader class="pb-3">
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0 space-y-1.5">
          <CardTitle class="flex items-center gap-2 text-lg">
            <Ticket class="size-5 shrink-0" />
            {{ t('vouchers.myTitle') }}
          </CardTitle>
          <CardDescription>{{ t('vouchers.howItWorks') }}</CardDescription>
        </div>
        <Button
          v-if="eventId"
          variant="ghost"
          size="sm"
          class="shrink-0"
          data-testid="btn-my-vouchers-details"
          @click="router.push({ name: 'my-vouchers', params: { eventId } })"
        >
          {{ t('vouchers.seeAll') }}
          <ArrowRight class="ml-1 size-4" />
        </Button>
      </div>
    </CardHeader>
    <CardContent class="space-y-4">
      <VoucherBalanceSummary :summary="account.summary" compact />
      <Button
        v-if="!authStore.selectedEvent?.is_expired"
        class="w-full sm:w-auto"
        :disabled="!canShowCode"
        data-testid="btn-show-voucher-code"
        @click="codeOpen = true"
      >
        <QrCode class="mr-2 size-4" />
        {{ t('vouchers.showCode') }}
      </Button>
      <p v-if="account.summary.available === 0" class="text-sm text-muted-foreground">
        {{ t('vouchers.noneAvailable') }}
      </p>
    </CardContent>
  </Card>

  <VoucherCodeDialog
    v-if="eventId"
    v-model:open="codeOpen"
    :event-id="eventId"
    @redeemed="load"
  />
</template>
