<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { VoucherBalance } from '@/client/types.gen'

/**
 * One person's vouchers at a glance: what they can use now, large, and where
 * that number comes from underneath.
 */
defineProps<{
  summary: VoucherBalance
  /** The smaller layout of the dashboard card. */
  compact?: boolean
  /** Someone else's balance (the organisers' view): no "you" in the wording. */
  other?: boolean
}>()

const { t } = useI18n()
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-baseline gap-2">
      <span
        class="font-bold tabular-nums"
        :class="compact ? 'text-3xl' : 'text-5xl'"
        data-testid="voucher-available"
      >
        {{ summary.available }}
      </span>
      <span class="text-sm text-muted-foreground">
        {{ t('vouchers.availableCaption', summary.available) }}
      </span>
    </div>

    <dl class="grid max-w-md grid-cols-3 gap-3 text-sm">
      <div>
        <dt class="text-xs text-muted-foreground">{{ t('vouchers.earned') }}</dt>
        <dd class="font-semibold tabular-nums" data-testid="voucher-earned">
          {{ summary.earned }}
        </dd>
      </div>
      <div>
        <dt class="text-xs text-muted-foreground">{{ t('vouchers.used') }}</dt>
        <dd class="font-semibold tabular-nums" data-testid="voucher-used">
          {{ summary.redeemed }}
        </dd>
      </div>
      <div>
        <dt class="text-xs text-muted-foreground">{{ t('vouchers.adjusted') }}</dt>
        <dd class="font-semibold tabular-nums">
          {{ summary.adjusted > 0 ? `+${summary.adjusted}` : summary.adjusted }}
        </dd>
      </div>
    </dl>

    <p v-if="summary.upcoming > 0" class="text-sm text-muted-foreground">
      {{ t(other ? 'vouchers.upcomingOther' : 'vouchers.upcoming', { n: summary.upcoming }) }}
    </p>
  </div>
</template>
