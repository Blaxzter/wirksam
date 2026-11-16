<script setup lang="ts">
/**
 * A task as the tasks tab names it: its name, "3 shifts · 17–19 July · Hall",
 * who is in charge, and why a task only a team can book is never shared.
 */
import { computed } from 'vue'

import { Lock } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useSharedListText } from '@/components/shared-lists/sharedListText'

import type { SharedListTaskRow } from '@/client/types.gen'

const props = defineProps<{ row: SharedListTaskRow }>()

const { t } = useI18n()
const { daysText, joinList } = useSharedListText()

const facts = computed(() =>
  [
    t('sharedLists.tasks.shifts', { count: props.row.shift_count }, props.row.shift_count),
    daysText(props.row.dates),
    props.row.location ?? '',
  ]
    .filter(Boolean)
    .join(' · '),
)
</script>

<template>
  <div class="grid min-w-0 gap-0.5 whitespace-normal">
    <span class="font-semibold" data-testid="task-name">{{ props.row.name }}</span>
    <span class="text-[12.5px] text-muted-foreground">{{ facts }}</span>
    <span v-if="props.row.manager_names.length > 0" class="text-[12.5px] text-muted-foreground">
      {{ t('sharedLists.tasks.managers', { names: joinList(props.row.manager_names) }) }}
    </span>
    <span
      v-if="props.row.team"
      class="flex items-start gap-1.5 text-[12.5px] text-warning"
      data-testid="task-team-locked"
    >
      <Lock class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
      {{ t('sharedLists.tasks.teamLocked', { team: props.row.team.name }) }}
    </span>
  </div>
</template>
