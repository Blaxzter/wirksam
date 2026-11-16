<script setup lang="ts">
/**
 * The lists of an event as a table, for a wide screen: status, the list,
 * places, sign-ups and when it closes, each sortable on the server, with a
 * checkbox per row for the bulk actions and a list's own buttons at the end.
 *
 * A row with something to fix gets a warning edge and the issue strip under
 * it, in a row of its own. Ended lists, and lists the viewer may only read,
 * cannot be ticked.
 */
import { useI18n } from 'vue-i18n'

import type { ListAction, ListSort } from '@/stores/sharedLists'

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
import TriStateCheckbox from '@/components/data-table/TriStateCheckbox.vue'
import SharedListIssueStrip from '@/components/shared-lists/SharedListIssueStrip.vue'
import SharedListRowActions from '@/components/shared-lists/SharedListRowActions.vue'
import SharedListStatusBadge from '@/components/shared-lists/SharedListStatusBadge.vue'
import SharedListTitleBlock from '@/components/shared-lists/SharedListTitleBlock.vue'
import { useSharedListText } from '@/components/shared-lists/sharedListText'
import { LIST_SORT_DIRS, isListSelectable } from '@/components/shared-lists/useSharedListActions'

import type { SharedListRow } from '@/client/types.gen'

const props = defineProps<{
  rows: readonly SharedListRow[]
  zone: string
  selection: RowSelection<SharedListRow>
  sort: ListSort
  dir: SortDir
  busyId: string | null
  copiedId: string | null
  /** The viewer may pause but not reopen or extend (`reshareLocked`). */
  locked?: boolean
  loading?: boolean
}>()

const emit = defineEmits<{
  sort: [key: ListSort]
  open: [row: SharedListRow]
  copy: [row: SharedListRow]
  act: [row: SharedListRow, action: ListAction]
}>()

const { t } = useI18n()
const { closesText } = useSharedListText()

const COLUMNS: { key: ListSort; labelKey: string; align?: 'end'; class?: string }[] = [
  { key: 'status', labelKey: 'sharedLists.table.columns.status', class: 'w-28' },
  { key: 'title', labelKey: 'sharedLists.table.columns.list' },
  { key: 'free', labelKey: 'sharedLists.table.columns.places', class: 'w-40' },
  { key: 'signups', labelKey: 'sharedLists.table.columns.signups', align: 'end', class: 'w-28' },
  {
    key: 'closes',
    labelKey: 'sharedLists.table.columns.closes',
    class: 'hidden w-36 xl:table-cell',
  },
]

/** The warning edge down the left of a row that has something to fix, and its strip. */
const ISSUE_EDGE = 'shadow-[inset_3px_0_0_var(--warning)]'
</script>

<template>
  <Table :aria-busy="props.loading || undefined" data-testid="shared-lists-table">
    <caption class="sr-only">
      {{
        t('sharedLists.table.caption')
      }}
    </caption>
    <TableHeader>
      <TableRow class="hover:bg-transparent">
        <TableHead class="w-10">
          <TriStateCheckbox
            :model-value="props.selection.headerState.value"
            :disabled="!props.selection.canSelect.value"
            :aria-label="t('sharedLists.table.selectAll')"
            data-testid="shared-lists-select-all"
            @update:model-value="(value) => props.selection.toggleAll(value === true)"
          />
        </TableHead>
        <SortableHead
          v-for="column in COLUMNS"
          :key="column.key"
          :label="t(column.labelKey)"
          :sort-key="column.key"
          :active-key="props.sort"
          :dir="props.dir"
          :default-dir="LIST_SORT_DIRS[column.key] ?? 'asc'"
          :align="column.align"
          :class="column.class"
          @sort="emit('sort', $event)"
        />
        <TableHead class="w-px">
          <span class="sr-only">{{ t('sharedLists.table.columns.actions') }}</span>
        </TableHead>
      </TableRow>
    </TableHeader>
    <TableBody>
      <template v-for="row in props.rows" :key="row.id">
        <TableRow
          :data-state="props.selection.isSelected(row.id) ? 'selected' : undefined"
          :class="row.issue ? ['border-b-0', ISSUE_EDGE] : ''"
          :data-list-id="row.id"
          :data-testid="`shared-list-row-${row.id}`"
        >
          <TableCell class="align-top">
            <Checkbox
              class="mt-1"
              :model-value="props.selection.isSelected(row.id)"
              :disabled="!isListSelectable(row)"
              :aria-label="t('sharedLists.table.selectRow', { title: row.title })"
              data-testid="shared-list-select"
              @update:model-value="(value) => props.selection.toggle(row.id, value === true)"
            />
          </TableCell>
          <TableCell class="align-top">
            <SharedListStatusBadge class="mt-0.5" :status="row.effective_status" />
          </TableCell>
          <TableCell class="min-w-56 align-top">
            <SharedListTitleBlock :row="row" :zone="props.zone" @open="emit('open', row)" />
          </TableCell>
          <TableCell class="align-top">
            <FillBar class="mt-1" :free="row.free" :cap="row.capacity" />
          </TableCell>
          <TableCell
            class="text-right align-top text-base font-bold tabular-nums"
            data-testid="shared-list-signups"
          >
            {{ row.signup_count }}
          </TableCell>
          <TableCell class="hidden align-top text-[13px] text-muted-foreground xl:table-cell">
            {{ closesText(row) }}
          </TableCell>
          <TableCell class="align-top">
            <SharedListRowActions
              :row="row"
              variant="icons"
              :busy="props.busyId === row.id"
              :copied="props.copiedId === row.id"
              :locked="props.locked"
              @copy="emit('copy', row)"
              @pause="emit('act', row, 'pause')"
              @resume="emit('act', row, 'resume')"
              @open="emit('open', row)"
            />
          </TableCell>
        </TableRow>
        <TableRow v-if="row.issue" :class="['hover:bg-transparent', ISSUE_EDGE]">
          <TableCell />
          <TableCell colspan="6" class="pt-0 pb-3">
            <SharedListIssueStrip
              :issue="row.issue"
              :title="row.title"
              :status="row.effective_status"
              :busy="props.busyId === row.id"
              :locked="props.locked"
              @fix="emit('act', row, $event)"
            />
          </TableCell>
        </TableRow>
      </template>
    </TableBody>
  </Table>
</template>
