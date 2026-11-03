<script setup lang="ts">
import { computed } from 'vue'

import { ChevronRight, QrCode, Ticket } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import Button from '@/components/ui/button/Button.vue'

import VoucherBalanceSummary from '@/components/vouchers/VoucherBalanceSummary.vue'

import type { VoucherAccount } from '@/client/types.gen'

/**
 * The volunteer's vouchers on the bookings page, beside their hours.
 *
 * Purely presentational: the page loads the account (`useMyVoucherAccount`,
 * which it also needs for the "+2 vouchers" on each booking) and decides
 * whether this shows at all. It reads the width of the `@container` the page
 * puts it in: narrow, it is a tile next to the hours tile with the number,
 * "available, +4 to come" and the code button; from `@2xl` up it is the full
 * card with the numbers block of "My vouchers".
 *
 * The code button stays when nothing is available, disabled, as on the
 * dashboard; after the event it goes, and the link to the history remains.
 */
const props = defineProps<{
  account: VoucherAccount
  eventId: string
  expired: boolean
  canShowCode: boolean
}>()

const emit = defineEmits<{ showCode: [] }>()

const { t } = useI18n()

const summary = computed(() => props.account.summary)

/** The tile has room for one line: "available, +4 to come". */
const availableShort = computed(() => {
  const n = summary.value.upcoming
  const available = t('vouchers.availableShort')
  return n > 0 ? `${available}, ${t('vouchers.upcomingShort', { n }, n)}` : available
})

const to = computed(() => ({ name: 'my-vouchers', params: { eventId: props.eventId } }))
</script>

<template>
  <section
    data-testid="my-vouchers-card"
    aria-labelledby="bookings-vouchers-title"
    class="flex min-w-0 flex-col rounded-2xl border bg-card p-4 text-card-foreground @2xl:rounded-[22px] @2xl:p-6"
  >
    <div class="flex items-center justify-between gap-1 @2xl:gap-2">
      <h2
        id="bookings-vouchers-title"
        class="flex min-w-0 items-center gap-1.5 text-[13px] font-semibold text-muted-foreground @2xl:gap-2 @2xl:text-base @2xl:font-bold @2xl:text-card-foreground"
      >
        <Ticket class="size-4 shrink-0 @2xl:size-[18px]" aria-hidden="true" />
        <span class="truncate @2xl:hidden">{{ t('vouchers.title') }}</span>
        <span class="hidden truncate @2xl:inline">{{ t('vouchers.yours') }}</span>
      </h2>
      <!-- A chevron in the tile, "History" on the card; 44 px either way. -->
      <RouterLink
        :to="to"
        :aria-label="t('vouchers.historyLink')"
        data-testid="btn-my-vouchers-details"
        class="-my-3 -mr-3 flex size-11 shrink-0 items-center justify-center rounded-lg text-muted-foreground outline-none hover:text-primary focus-visible:ring-[3px] focus-visible:ring-ring/50 @2xl:hidden"
      >
        <ChevronRight class="size-4" aria-hidden="true" />
      </RouterLink>
      <RouterLink
        :to="to"
        class="-my-2 hidden min-h-8 items-center rounded-md px-1 text-sm font-semibold text-primary outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50 @2xl:flex"
      >
        {{ t('vouchers.history.title') }}
      </RouterLink>
    </div>

    <!-- The tile: the number and one line -->
    <div class="@2xl:hidden">
      <p class="mt-1.5 text-[2rem] leading-none font-bold tabular-nums">
        {{ summary.available }}
      </p>
      <p class="mt-1 text-[13px] text-muted-foreground" data-testid="my-vouchers-available-short">
        {{ availableShort }}
      </p>
    </div>
    <!-- The card: the numbers block -->
    <VoucherBalanceSummary class="mt-3.5 hidden @2xl:block" :summary="summary" />

    <div class="mt-auto pt-3 @2xl:pt-4">
      <Button
        v-if="!expired"
        data-testid="btn-show-voucher-code"
        :disabled="!canShowCode"
        class="h-auto min-h-11 w-full rounded-[10px] px-3 py-2 text-sm leading-tight font-semibold whitespace-normal @2xl:h-[46px] @2xl:min-h-0 @2xl:rounded-xl @2xl:py-0 @2xl:text-[15px] @2xl:font-bold"
        @click="emit('showCode')"
      >
        <QrCode class="hidden @2xl:block" aria-hidden="true" />
        {{ t('vouchers.showCode') }}
      </Button>
    </div>
  </section>
</template>
