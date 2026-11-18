<script setup lang="ts">
/**
 * A shared list's guest's vouchers in one event, on their manage page: what
 * they can use now, what their booked shifts will still bring, the code to
 * show at a stand, and where the vouchers came from and went.
 *
 * The same pieces as a member's "My vouchers" page. The history comes without
 * the names of whoever redeemed or corrected, and without the organisers'
 * notes: a guest page shows neither. The code comes through the guest's link
 * (`source`), and the page reloads once one was used, or once that link
 * turned out to be dead.
 */
import { computed, ref, useId, watch } from 'vue'

import { QrCode, Ticket } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'

import VoucherBalanceSummary from '@/components/vouchers/VoucherBalanceSummary.vue'
import VoucherCodeDialog from '@/components/vouchers/VoucherCodeDialog.vue'
import VoucherHistory from '@/components/vouchers/VoucherHistory.vue'

import type { GuestVoucherAccount } from '@/client/types.gen'
import type { VoucherPassSource } from '@/lib/vouchers'

const props = withDefaults(
  defineProps<{
    voucher: GuestVoucherAccount
    source: VoucherPassSource
    /** The guest has vouchers in more than one event: each card names its own. */
    named?: boolean
  }>(),
  { named: false },
)

const emit = defineEmits<{
  /** A code was used at a stand: the balance on the page is out of date. */
  redeemed: []
  /** The code screen closed on a link that no longer works. */
  gone: []
}>()

const { t } = useI18n()
const uid = useId()

const codeOpen = ref(false)
let wentDead = false

const summary = computed(() => props.voucher.account.summary)
const nothingToShow = computed(() => summary.value.available === 0)

/**
 * Why the button does nothing yet: before the first shift is over, the
 * vouchers are still to come; afterwards they were used up.
 */
const emptyText = computed(() =>
  summary.value.earned > 0 || summary.value.adjusted !== 0
    ? t('vouchers.noneAvailable')
    : t('guestSignup.manage.vouchers.nothingYet'),
)

const title = computed(() =>
  props.named
    ? t('guestSignup.manage.vouchers.titleEvent', { event: props.voucher.event_name })
    : t('guestSignup.manage.vouchers.title'),
)

function showCode(): void {
  if (nothingToShow.value) return
  codeOpen.value = true
}

function onGone(): void {
  wentDead = true
}

// Told once the dialog is closed, so the page swaps under nobody's feet.
watch(codeOpen, (isOpen) => {
  if (isOpen || !wentDead) return
  wentDead = false
  emit('gone')
})
</script>

<template>
  <section
    class="space-y-4 rounded-xl border bg-card p-4"
    :aria-labelledby="`${uid}-title`"
    data-testid="guest-vouchers"
    :data-event-id="voucher.event_id"
  >
    <h2 :id="`${uid}-title`" class="flex items-center gap-2 text-lg font-semibold break-words">
      <Ticket class="size-5 shrink-0" aria-hidden="true" />
      {{ title }}
    </h2>

    <VoucherBalanceSummary :summary="summary" compact />

    <div class="space-y-2">
      <!-- aria-disabled rather than disabled: after a redemption took the last
           voucher, the closing code screen hands focus back to this button. -->
      <Button
        class="h-12 w-full rounded-xl text-base font-bold aria-disabled:opacity-50"
        :aria-disabled="nothingToShow || undefined"
        :aria-describedby="nothingToShow ? `${uid}-empty` : `${uid}-how`"
        data-testid="btn-guest-show-code"
        @click="showCode"
      >
        <QrCode class="size-[18px]" aria-hidden="true" />
        {{ t('guestSignup.manage.vouchers.showCode') }}
      </Button>
      <p
        v-if="nothingToShow"
        :id="`${uid}-empty`"
        class="text-sm text-muted-foreground"
        data-testid="guest-vouchers-empty"
      >
        {{ emptyText }}
      </p>
      <p :id="`${uid}-how`" class="text-sm text-muted-foreground">
        {{ t('guestSignup.manage.vouchers.howTo') }}
      </p>
    </div>

    <VoucherHistory :account="voucher.account" with-upcoming class="-mx-2" />

    <VoucherCodeDialog
      v-model:open="codeOpen"
      :source="source"
      @redeemed="emit('redeemed')"
      @gone="onGone"
    />
  </section>
</template>
