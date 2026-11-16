<script setup lang="ts">
/**
 * The tasks tab on a phone: one card per task with its places and where they
 * are shared, and a checkbox to share several tasks as one list.
 */
import { useI18n } from 'vue-i18n'

import type { RowSelection } from '@/composables/useRowSelection'

import { Checkbox } from '@/components/ui/checkbox'

import FillBar from '@/components/data-table/FillBar.vue'
import SharedListTaskSummary from '@/components/shared-lists/SharedListTaskSummary.vue'
import TaskSharedInCell from '@/components/shared-lists/TaskSharedInCell.vue'

import type { SharedListTaskRow } from '@/client/types.gen'

const props = defineProps<{
  rows: readonly SharedListTaskRow[]
  selection: RowSelection<SharedListTaskRow>
  loading?: boolean
}>()

const emit = defineEmits<{
  open: [listId: string]
  share: [taskId: string]
}>()

const { t } = useI18n()
</script>

<template>
  <ul
    class="grid gap-2.5"
    :aria-label="t('sharedLists.tasks.caption')"
    :aria-busy="props.loading || undefined"
    data-testid="shared-list-tasks-cards"
  >
    <li
      v-for="row in props.rows"
      :key="row.id"
      class="flex items-start gap-1 rounded-xl border py-3 pr-3 pl-1"
      :class="[
        row.team ? 'bg-muted/40' : 'bg-card',
        props.selection.isSelected(row.id) ? 'ring-1 ring-primary' : '',
      ]"
      :data-testid="`shared-list-task-${row.id}`"
    >
      <!-- The label gives the small box a thumb-sized target. -->
      <label class="flex size-11 shrink-0 items-center justify-center">
        <Checkbox
          :model-value="props.selection.isSelected(row.id)"
          :disabled="!row.can_share"
          :aria-label="t('sharedLists.tasks.selectRow', { name: row.name })"
          data-testid="shared-list-task-select"
          @update:model-value="(value) => props.selection.toggle(row.id, value === true)"
        />
      </label>
      <div class="grid min-w-0 flex-1 gap-2.5 pt-2.5">
        <SharedListTaskSummary :row="row" />
        <FillBar :free="row.free" :cap="row.capacity" />
        <TaskSharedInCell :row="row" @open="emit('open', $event)" @share="emit('share', $event)" />
      </div>
    </li>
  </ul>
</template>
