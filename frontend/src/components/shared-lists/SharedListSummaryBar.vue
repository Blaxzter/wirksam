<script setup lang="ts">
/** The four figures over the lists: open lists, sign-ups, guests, free places. */
import { computed } from 'vue'

import { useI18n } from 'vue-i18n'

import type { SharedListSummary } from '@/client/types.gen'

const props = defineProps<{ summary: SharedListSummary }>()

const { t } = useI18n()

const figures = computed(() => [
  {
    key: 'live',
    value: props.summary.live_lists,
    label: t('sharedLists.summary.liveLists', props.summary.live_lists),
  },
  {
    key: 'signups',
    value: props.summary.signups,
    label: t('sharedLists.summary.signups', props.summary.signups),
  },
  {
    key: 'guests',
    value: props.summary.guests,
    label: t('sharedLists.summary.guests', props.summary.guests),
  },
  {
    key: 'free',
    value: props.summary.free_in_live,
    label: t('sharedLists.summary.freeInLive', props.summary.free_in_live),
  },
])
</script>

<template>
  <dl
    class="grid grid-cols-2 gap-x-6 gap-y-3 rounded-xl border bg-card px-4 py-3.5 sm:flex sm:flex-wrap sm:gap-x-10"
    :aria-label="t('sharedLists.summary.label')"
    data-testid="shared-lists-summary"
  >
    <div v-for="figure in figures" :key="figure.key" class="flex min-w-0 flex-col-reverse">
      <dt class="text-[13px] leading-snug text-muted-foreground">{{ figure.label }}</dt>
      <dd
        class="text-[22px] leading-tight font-bold tabular-nums"
        :data-testid="`shared-lists-summary-${figure.key}`"
      >
        {{ figure.value }}
      </dd>
    </div>
  </dl>
</template>
