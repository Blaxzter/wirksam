<script setup lang="ts">
/**
 * The event's tasks with shifts ahead and where their places are shared, as
 * a table for a wide screen: sortable by name, free places and places on no
 * list. A task only a team can book cannot be ticked.
 */
import { useI18n } from 'vue-i18n'

import type { TaskSort } from '@/stores/sharedLists'

import type { RowSelection } from '@/composables/useRowSelection'
import type { SortDir } from '@/composables/useTableQuery'

import { Checkbox } from '@/components/ui/checkbox'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

import FillBar from '@/components/data-table/FillBar.vue'
import SortableHead from '@/components/data-table/SortableHead.vue'
import TableCard from '@/components/data-table/TableCard.vue'
import TriStateCheckbox from '@/components/data-table/TriStateCheckbox.vue'
import SharedListTaskSummary from '@/components/shared-lists/SharedListTaskSummary.vue'
import TaskSharedInCell from '@/components/shared-lists/TaskSharedInCell.vue'

import type { SharedListTaskRow } from '@/client/types.gen'

const props = defineProps<{
  rows: readonly SharedListTaskRow[]
  selection: RowSelection<SharedListTaskRow>
  sort: TaskSort
  dir: SortDir
  loading?: boolean
}>()

const emit = defineEmits<{
  sort: [key: TaskSort]
  open: [listId: string]
  share: [taskId: string]
}>()

const { t } = useI18n()
</script>

<template>
  <TableCard>
    <Table :aria-busy="props.loading || undefined" data-testid="shared-list-tasks-table">
      <caption class="sr-only">
        {{
          t('sharedLists.tasks.caption')
        }}
      </caption>
      <TableHeader>
        <TableRow class="hover:bg-transparent">
          <TableHead class="w-10">
            <TriStateCheckbox
              :model-value="props.selection.headerState.value"
              :disabled="!props.selection.canSelect.value"
              :aria-label="t('sharedLists.tasks.selectAll')"
              data-testid="shared-list-tasks-select-all"
              @update:model-value="(value) => props.selection.toggleAll(value === true)"
            />
          </TableHead>
          <SortableHead
            :label="t('sharedLists.tasks.columns.task')"
            sort-key="name"
            :active-key="props.sort"
            :dir="props.dir"
            @sort="emit('sort', $event)"
          />
          <SortableHead
            :label="t('sharedLists.tasks.columns.places')"
            sort-key="free"
            :active-key="props.sort"
            :dir="props.dir"
            default-dir="desc"
            class="w-44"
            @sort="emit('sort', $event)"
          />
          <SortableHead
            :label="t('sharedLists.tasks.columns.sharedIn')"
            sort-key="unlisted_free"
            :active-key="props.sort"
            :dir="props.dir"
            default-dir="desc"
            class="w-[38%]"
            @sort="emit('sort', $event)"
          />
        </TableRow>
      </TableHeader>
      <TableBody>
        <TableRow
          v-for="row in props.rows"
          :key="row.id"
          :data-state="props.selection.isSelected(row.id) ? 'selected' : undefined"
          :class="row.team ? 'bg-muted/40' : ''"
          :data-testid="`shared-list-task-${row.id}`"
        >
          <TableCell class="align-top">
            <Checkbox
              class="mt-1"
              :model-value="props.selection.isSelected(row.id)"
              :disabled="!row.can_share"
              :aria-label="t('sharedLists.tasks.selectRow', { name: row.name })"
              data-testid="shared-list-task-select"
              @update:model-value="(value) => props.selection.toggle(row.id, value === true)"
            />
          </TableCell>
          <TableCell class="align-top">
            <SharedListTaskSummary :row="row" />
          </TableCell>
          <TableCell class="align-top">
            <FillBar class="mt-1" :free="row.free" :cap="row.capacity" />
          </TableCell>
          <TableCell class="align-top">
            <TaskSharedInCell
              :row="row"
              @open="emit('open', $event)"
              @share="emit('share', $event)"
            />
          </TableCell>
        </TableRow>
      </TableBody>
    </Table>
  </TableCard>
</template>
