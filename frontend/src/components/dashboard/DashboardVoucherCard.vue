<script setup lang="ts">
/**
 * The volunteer's vouchers, beside the next shift.
 *
 * Purely presentational: the account comes from `useMyVoucherAccount` in the
 * page, which also decides whether this is mounted at all (the same rule as
 * `MyVouchersCard`: not in an event without vouchers). On desktop it is the
 * side card "Your vouchers" with the numbers block of "My vouchers"
 * (`VoucherBalanceSummary`), so the balance reads the same on every page;
 * when the page is narrower than its `@4xl` container width it shrinks to a
 * tile next to the "Signed up" tile, with only the number, the line under it
 * and the code button, because those are what you need at the stand.
 *
 * The code button stays when nothing is available, disabled, as on the
 * bookings page; the big "0 available" already says why. After the event it
 * goes, and the history link remains.
 *
 * As a phone tile it stretches to the height of the tile beside it, the
 * button pinned to the bottom of both. As the desktop side card it keeps its
 * own height (`@4xl:self-start`): stretched to the next-shift card, which is
 * taller once it has a map button, it left a hole between the numbers and
 * the button.
 */
import { computed } from 'vue'

import { ChevronRight, QrCode, Ticket } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'

import VoucherBalanceSummary from '@/components/vouchers/VoucherBalanceSummary.vue'

import type { VoucherAccount } from '@/client/types.gen'

const props = defineProps<{
  account: VoucherAccount
  eventId: string
  expired: boolean
  canShowCode: boolean
}>()

const emit = defineEmits<{ showCode: [] }>()

const { t } = useI18n()

const summary = computed(() => props.account.summary)

/** The phone tile has room for one line: "available, +2 to come", as on the bookings page. */
const availableShort = computed(() => {
  const n = summary.value.upcoming
  const available = t('vouchers.availableShort')
  return n > 0 ? `${available}, ${t('vouchers.upcomingShort', { n }, n)}` : available
})
</script>

<template>
  <section
    data-testid="my-vouchers-card"
    aria-labelledby="dashboard-vouchers-title"
    class="flex min-w-0 flex-col rounded-2xl border bg-card p-4 text-card-foreground @4xl:gap-1.5 @4xl:self-start @4xl:rounded-[22px] @4xl:p-6"
  >
    <div class="flex items-center justify-between gap-2">
      <h2
        id="dashboard-vouchers-title"
        class="flex min-w-0 items-center gap-1.5 text-[13px] font-semibold text-muted-foreground @4xl:gap-2 @4xl:text-base @4xl:font-bold @4xl:text-card-foreground"
      >
        <Ticket class="size-4 shrink-0 @4xl:size-[18px]" aria-hidden="true" />
        <span class="truncate @4xl:hidden">{{ t('vouchers.title') }}</span>
        <span class="hidden truncate @4xl:inline">{{ t('dashboard.home.vouchers.title') }}</span>
      </h2>
      <!--
        In the phone tile the word "History" left "Vouchers" no room at 360 px
        ("Vouch…"), so there it is a chevron with the word for screen readers;
        the 44 px target reaches into the card's padding.
      -->
      <RouterLink
        data-testid="btn-my-vouchers-details"
        :to="{ name: 'my-vouchers', params: { eventId } }"
        class="-my-3 -mr-3 flex size-11 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:text-primary focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none @4xl:-my-2 @4xl:mr-0 @4xl:size-auto @4xl:py-2 @4xl:text-sm @4xl:font-semibold @4xl:text-primary @4xl:hover:underline"
      >
        <ChevronRight class="size-4 @4xl:hidden" aria-hidden="true" />
        <span class="sr-only @4xl:not-sr-only">{{ t('dashboard.home.vouchers.history') }}</span>
      </RouterLink>
    </div>

    <!-- The tile: the number and one line -->
    <div class="@4xl:hidden">
      <p
        data-testid="dashboard-voucher-available"
        class="mt-1.5 text-[2rem] leading-none font-bold tabular-nums"
      >
        {{ summary.available }}
      </p>
      <p data-testid="dashboard-voucher-available-short" class="text-[13px] text-muted-foreground">
        {{ availableShort }}
      </p>
    </div>
    <!-- The card: the numbers block of "My vouchers" -->
    <VoucherBalanceSummary class="mt-3.5 hidden @4xl:block" :summary="summary" />

    <!--
      The phone tile is 104 px wide inside at 320 px, less than the icon and
      "Show my code" need on one line, so there the icon goes and the label
      may wrap rather than spill past the button's edges.
    -->
    <div class="mt-auto pt-3 @4xl:pt-4">
      <Button
        v-if="!expired"
        data-testid="btn-show-voucher-code"
        :disabled="!canShowCode"
        class="h-auto min-h-11 w-full rounded-lg px-3 py-2 text-center text-sm leading-tight font-semibold whitespace-normal @4xl:h-[46px] @4xl:min-h-0 @4xl:rounded-xl @4xl:py-0 @4xl:font-bold @4xl:whitespace-nowrap"
        @click="emit('showCode')"
      >
        <QrCode class="hidden @4xl:block" aria-hidden="true" />
        {{ t('vouchers.showCode') }}
      </Button>
    </div>
  </section>
</template>
