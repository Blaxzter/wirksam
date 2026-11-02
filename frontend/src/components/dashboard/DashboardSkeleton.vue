<script setup lang="ts">
/**
 * The dashboard's shape while the feed and the voucher account load: the next
 * shift with the tiles beside or under it, the plan, and a row of open-shift
 * cards. Matching the real layout keeps the page from jumping when the cards
 * arrive. The header is not part of it; it needs no data and is already there.
 */
import { useI18n } from 'vue-i18n'

import { Skeleton } from '@/components/ui/skeleton'

const { t } = useI18n()
</script>

<template>
  <div
    data-testid="dashboard-loading"
    aria-busy="true"
    :aria-label="t('common.states.loading')"
    role="status"
    class="space-y-5 lg:space-y-6"
  >
    <div class="grid grid-cols-2 gap-x-3 gap-y-5 lg:grid-cols-3 lg:gap-6">
      <Skeleton class="col-span-2 h-[19rem] rounded-[20px] lg:h-[21rem] lg:rounded-[22px]" />
      <Skeleton class="h-44 rounded-2xl lg:h-[21rem] lg:rounded-[22px]" />
      <Skeleton class="h-44 rounded-2xl lg:hidden" />
    </div>
    <div class="grid gap-5 lg:grid-cols-3 lg:gap-6">
      <Skeleton class="h-56 rounded-2xl lg:col-span-2 lg:h-72 lg:rounded-[22px]" />
      <Skeleton class="hidden h-72 rounded-[22px] lg:block" />
    </div>
    <div class="space-y-3">
      <Skeleton class="h-5 w-48" />
      <div class="grid gap-2.5 sm:grid-cols-2 sm:gap-3 lg:grid-cols-3 lg:gap-4">
        <Skeleton class="h-40 rounded-2xl lg:h-44 lg:rounded-[18px]" />
        <Skeleton class="h-40 rounded-2xl lg:h-44 lg:rounded-[18px]" />
        <Skeleton class="h-40 rounded-2xl max-sm:hidden lg:h-44 lg:rounded-[18px]" />
      </div>
    </div>
  </div>
</template>
